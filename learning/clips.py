"""SC 本編のシーン音声から、文を切り出す。

無音区間（内部の間）を文の切れ目の候補にし、切った音声は Gemini に書き起こさせて、
狙った文と一致するかを確かめる。照合は文字単位の類似度で行い、固有名詞の綴りの揺れや
書き起こしの聞き違いは許容する。前後の文が混ざる・文の一部が欠ける場合は、一致度が下がって弾かれる。
"""
import difflib
import hashlib
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from audio_check import ask

CACHE_DIR = Path(__file__).parent / "cache"
SILENCE_DB = "-40dB"
SILENCE_MIN = 0.12
SENSITIVE_DB = "-30dB"  # 1回目で一致しない文だけ、短い間も切れ目の候補にして探し直す
SENSITIVE_MIN = 0.05
PAD = 0.08  # 切り口の前後に残す余白（秒）
ACCEPT = 0.85  # これ以上の一致度なら、その切り出しを採用する
GOOD = 0.95  # これ以上なら、ほかの候補を試さずに確定する
EDGE_PENALTY = 0.15  # 文の最初か最後の単語が聞こえていないときの減点


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit(1)
    return r.stderr


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout)


def silences(path: Path, db: str = SILENCE_DB, min_len: float = SILENCE_MIN) -> list[tuple[float, float]]:
    log = run(["ffmpeg", "-i", str(path), "-af", f"silencedetect=n={db}:d={min_len}", "-f", "null", "-"])
    st = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    if len(en) < len(st):
        en.append(duration(path))
    return list(zip(st, en))


def _norm(s: str) -> str:
    """英字と数字だけにそろえる（大文字小文字・長音符・ハイフン・句読点の揺れを無視する）。"""
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^a-z0-9]", "", s)


def _words(s: str) -> list[str]:
    return [w for w in (_norm(x) for x in s.split()) if w]


def _match_score(target: str, heard: str) -> float:
    """狙った文と書き起こしの、文字単位の類似度。長さの差の分だけ下がる。"""
    t, h = _norm(target), _norm(heard)
    if not t or not h:
        return 0.0
    return difflib.SequenceMatcher(None, t, h, autojunk=False).ratio()


def _edge_ok(target: str, heard: str) -> bool:
    """文の最初と最後の単語が、書き起こしの最初と最後に聞こえているか。"""
    t, h = _words(target), _norm(heard)
    if not t or not h:
        return False

    def has(word: str, window: str) -> bool:
        if len(word) < 5:  # 短い語は聞き違いが多いので、ここでは判定しない
            return True
        m = difflib.SequenceMatcher(None, word, window, autojunk=False).find_longest_match(0, len(word), 0, len(window))
        return m.size >= 0.6 * len(word)

    return has(t[-1], h[-(len(t[-1]) + 3):]) and has(t[0], h[:len(t[0]) + 3])


def _transcribe(path: Path, strong: bool = False) -> str:
    if strong:
        # 長い間のあとの後半が書き起こされないことがあるので、最後まで書くよう念を押す
        return ask(path, "Transcribe this English audio completely, from the first word to the very last word. "
                         "The speaker may pause for a second or more in the middle of a sentence; keep transcribing "
                         "after every pause. Output only the transcript.")
    return ask(path, "Transcribe this English audio exactly. Output only the transcript.")


def split_sentences(narration: str) -> list[str]:
    return [x for x in re.split(r'(?<=[.?!])\s+(?=[A-Z"])', narration.strip()) if x]


def _clip_path(scene_wav: Path, sentence: str) -> Path:
    key = hashlib.sha1(f"{scene_wav}|{sentence}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"clip_{key}.wav"


def _cut(scene_wav: Path, a: float, b: float, out: Path):
    run(["ffmpeg", "-y", "-i", str(scene_wav), "-ss", f"{max(0, a - PAD):.3f}", "-to", f"{b + PAD:.3f}",
         "-af", "afade=t=in:d=0.03,areverse,afade=t=in:d=0.05,areverse", str(out)])


def cut_scene_sentences(scene_wav: Path, narration: str) -> list[Path]:
    """1シーンの全文を、文ごとの音声に切り分けて返す（順番は narration の文の順）。

    前の文の終わりから、次の文の終わり候補（内部の無音の中点）を1つずつ伸ばしながら、
    Gemini で書き起こして狙った文と照合し、いちばん一致した候補で確定する。
    セミコロンなど文の途中の間を、文の切れ目と取り違えないための方式。
    """
    sents = split_sentences(narration)
    paths = [_clip_path(scene_wav, s) for s in sents]
    if all(p.exists() for p in paths):  # 確定した切り出しだけがここに保存されるので、そのまま使う
        return paths

    total = duration(scene_wav)
    sil = silences(scene_wav)
    speech_start = sil[0][1] if sil and sil[0][0] <= 0.05 else 0.0
    speech_end = sil[-1][0] if sil and sil[-1][1] >= total - 0.05 else total
    span = speech_end - speech_start

    def candidates(sl):
        return [(a + b) / 2 for a, b in sl if speech_start < a and b < speech_end]

    tiers = [candidates(sil), candidates(silences(scene_wav, SENSITIVE_DB, SENSITIVE_MIN))]

    start = speech_start
    for i, sent in enumerate(sents):
        tmp = CACHE_DIR / f"tmp_{paths[i].stem}.wav"
        best = None
        tried = []
        for cands in tiers:
            if i == len(sents) - 1:
                ends = [speech_end]
            else:
                done_chars = sum(len(x) + 1 for x in sents[:i + 1])
                exp_e = speech_start + span * done_chars / len(narration)
                lo = start + 0.8
                lo_try = start + (exp_e - start) * 0.65  # 期待位置よりかなり手前の候補は、試さない
                ends = [c for c in cands if c >= max(lo, lo_try) and c <= exp_e + (exp_e - start) * 0.8 + 1.5]
                if not ends:
                    ends = [c for c in cands if c >= lo][:3]
            ends = [e for e in ends if all(abs(e - t) > 0.05 for t in tried)]
            for e in ends:
                tried.append(e)
                _cut(scene_wav, start, e, tmp)
                heard = _transcribe(tmp)
                score = _match_score(sent, heard)
                if not _edge_ok(sent, heard):
                    score -= EDGE_PENALTY
                if best is None or score > best[0]:
                    best = (score, e, heard)
                if score >= GOOD:
                    break
                # 狙った文より長く聞こえ始めたら、それ以上伸ばしても改善しない
                if len(_norm(heard)) > len(_norm(sent)) * 1.25 + 8:
                    break
            if best is not None and best[0] < ACCEPT:
                # 書き起こしが途中で切れた可能性があるので、いちばん良かった候補だけ、念押しでやり直す
                _cut(scene_wav, start, best[1], tmp)
                heard = _transcribe(tmp, strong=True)
                score = _match_score(sent, heard)
                if not _edge_ok(sent, heard):
                    score -= EDGE_PENALTY
                if score > best[0]:
                    best = (score, best[1], heard)
            if best is not None and best[0] >= ACCEPT:
                break
        tmp.unlink(missing_ok=True)
        if best is None or best[0] < ACCEPT:
            print(f"切り出しが一致しません（一致度 {best[0] if best else 0:.2f}）: {sent}\n  聞こえた文: {best[2] if best else ''}")
            sys.exit(1)
        _cut(scene_wav, start, best[1], paths[i])
        start = best[1]
    return paths


def sentence_spans(scene_wav: Path, clip_paths: list[Path]) -> list[tuple[float, float]]:
    """シーン音声の中での、各文の（開始, 終了）秒。通しの字幕に使う。
    切り出しは、話し始めから順につなぎ目なく切っているので、各クリップの長さ（前後の余白を除く）を足し上げればよい。"""
    sil = silences(scene_wav)
    t = sil[0][1] if sil and sil[0][0] <= 0.05 else 0.0
    spans = []
    for p in clip_paths:
        d = max(0.1, duration(p) - 2 * PAD)
        spans.append((round(t, 3), round(t + d, 3)))
        t += d
    return spans
