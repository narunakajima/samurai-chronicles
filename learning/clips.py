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


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _numwords(s: str) -> str:
    """0〜99 の英単語（twenty-nine など）を数字にそろえる。書き起こしが「29」と書くことがあるため（ep113）。"""
    for t in range(2, 10):
        for o in range(1, 10):
            s = re.sub(rf"\b{_TENS[t]}[- ]{_ONES[o]}\b", str(t * 10 + o), s)
    for t in range(2, 10):
        s = re.sub(rf"\b{_TENS[t]}\b", str(t * 10), s)
    for n in range(19, -1, -1):
        s = re.sub(rf"\b{_ONES[n]}\b", str(n), s)
    s = re.sub(r"\b(twent|thirt|fort|fift|sixt|sevent|eight|ninet)ies\b",
               lambda m: {"twent": "20", "thirt": "30", "fort": "40", "fift": "50", "sixt": "60", "sevent": "70", "eight": "80", "ninet": "90"}[m.group(1)] + "s", s)
    s = re.sub(r"\b(\w+teenth)\b", lambda m: {"thirteenth": "13th", "fourteenth": "14th", "fifteenth": "15th", "sixteenth": "16th",
                                                "seventeenth": "17th", "eighteenth": "18th", "nineteenth": "19th"}.get(m.group(1), m.group(1)), s)
    return s


def _norm(s: str) -> str:
    """英字と数字だけにそろえる（大文字小文字・長音符・ハイフン・句読点の揺れを無視する）。"""
    s = unicodedata.normalize("NFKD", _numwords(s.lower()))
    return re.sub(r"[^a-z0-9]", "", s)


def _words(s: str) -> list[str]:
    return [w for w in (_norm(x) for x in s.split()) if w]


def _match_score(target: str, heard: str) -> float:
    """狙った文と書き起こしの、文字単位の類似度。長さの差の分だけ下がる。"""
    t, h = _norm(target), _norm(heard)
    if not t or not h:
        return 0.0
    return difflib.SequenceMatcher(None, t, h, autojunk=False).ratio()


def _score_ignoring_names(target: str, heard: str) -> float:
    """書き起こしが固有名詞を聞き違えた箇所（Seimei's → Same as など）だけを無視した一致度。
    狙った文の大文字始まりの語が、書き起こしの別の語（3語まで）に置き換わっている・まるごと落ちている（2語まで）ところだけを、外して比べる。"""
    T, H = target.split(), heard.split()
    nT, nH = [_norm(w) for w in T], [_norm(w) for w in H]
    kt, kh = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, nT, nH, autojunk=False).get_opcodes():
        if tag == "replace" and (j2 - j1) <= 3 and all(T[k][:1].isupper() for k in range(i1, i2)):
            continue
        if tag == "delete" and (i2 - i1) <= 2 and all(T[k][:1].isupper() for k in range(i1, i2)):
            continue   # 書き起こしが固有名詞をまるごと落とした（ep115: Sankin-kotai）
        kt += nT[i1:i2]
        kh += nH[j1:j2]
    a, b = "".join(kt), "".join(kh)
    if len(a) < 0.6 * len(_norm(target)) or not a or not b:   # 外し過ぎ（文の大半が一致していない）なら、この方法は使わない
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _score(target: str, heard: str) -> float:
    return max(_match_score(target, heard), _score_ignoring_names(target, heard))


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


_WHISPER = None
_WHISPER_LOCK = __import__("threading").Lock()   # ビルドは複数シーンを並列に処理するので、Whisper のモデルは1つずつ使う


def whisper_tail_ok(clip: Path, sent: str) -> bool:
    """切り出した音声を手元の Whisper で書き起こし、文の最後の語が、書き起こしの末尾に聞こえているか確かめる。
    Gemini は欠けた文末（短い語・数字）を補って書き起こすことがあるため、別の方式で確かめる（ep115: 「Edo Castle, 1722.」の 1722 が欠けた）。"""
    global _WHISPER
    import whisper
    with _WHISPER_LOCK:
        if _WHISPER is None:
            _WHISPER = whisper.load_model("small")
        text = _WHISPER.transcribe(str(clip), language="en", fp16=False)["text"]
    heard = [w for w in (_norm(x) for x in text.split()) if w]
    target = _words(sent)
    if not target or not heard:
        return False
    last = target[-1]
    return any(difflib.SequenceMatcher(None, last, h, autojunk=False).ratio() >= 0.7 for h in heard[-2:])


def whisper_boundaries(scene_wav: Path, sents: list):
    """シーン全体を Whisper で単語ごとの時刻にし、狙った文の単語と照らし合わせて、文と文の切れ目（秒）を返す。
    文の最後の語の終わりと、次の文の最初の語の始まりの、ちょうど中間。照合できなければ None（従来の方式にもどる）。
    Gemini の書き起こしだけでは、文末の年号や短い語の欠け・次の文の頭の混入を見逃した（ep115）ため。"""
    global _WHISPER
    import whisper
    with _WHISPER_LOCK:
        if _WHISPER is None:
            _WHISPER = whisper.load_model("small")
        r = _WHISPER.transcribe(str(scene_wav), language="en", word_timestamps=True, fp16=False)
    W = [(_norm(w["word"]), float(w["start"]), float(w["end"])) for seg in r["segments"] for w in seg["words"] if _norm(w["word"])]
    T, owner = [], []
    for i, sent in enumerate(sents):
        for w in _words(sent):
            T.append(w)
            owner.append(i)
    if not W or not T:
        return None
    mp = [None] * len(T)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, T, [w[0] for w in W], autojunk=False).get_opcodes():
        if tag == "equal":
            for d in range(i2 - i1):
                mp[i1 + d] = j1 + d
        elif tag == "replace":
            for d in range(i1, i2):
                mp[d] = j1 + min(j2 - j1 - 1, int((d - i1) * (j2 - j1) / (i2 - i1)))
    bounds = []
    for i in range(len(sents) - 1):
        last = max(k for k, o in enumerate(owner) if o == i)
        nxt = last + 1
        a, b = mp[last], mp[nxt]
        if a is None or b is None or b <= a:
            return None
        bounds.append((W[a][2] + W[b][1]) / 2 if W[b][1] > W[a][2] else (W[a][2] + W[b][1]) / 2)
    if any(y <= x for x, y in zip(bounds, bounds[1:])):
        return None
    return bounds


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

    try:
        wb = whisper_boundaries(scene_wav, sents)
    except Exception as ex:  # noqa: BLE001  Whisper が使えなくても、従来の方式で切り出せる
        print(f"  （Whisper の切れ目が使えません: {ex}）")
        wb = None
    tiers = ([None] if wb else []) + [candidates(sil), candidates(silences(scene_wav, SENSITIVE_DB, SENSITIVE_MIN))]

    def prev_tail_in_head(prev: str, heard: str) -> bool:
        """次の文の書き起こしの冒頭に、前の文の最後の語が混じっているか（前の文の終わりが早すぎた印）。"""
        pw = _words(prev)[-3:]
        pt, hn = "".join(pw), _norm(heard)
        if len(pt) < 8:
            return False
        head = hn[:len(pt) + 8]
        return difflib.SequenceMatcher(None, pt, head, autojunk=False).find_longest_match(0, len(pt), 0, len(head)).size >= 0.7 * len(pt)

    starts = []
    start = speech_start
    i = 0
    extended = set()
    while i < len(sents):
        sent = sents[i]
        tmp = CACHE_DIR / f"tmp_{paths[i].stem}.wav"
        best = None
        tried = []
        for cands in tiers:
            if i == len(sents) - 1:
                ends = [speech_end]
            elif cands is None:   # Whisper の単語の時刻から決めた切れ目
                ends = [wb[i]] if wb[i] > start + 0.3 else []
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
                score = _score(sent, heard)
                if not _edge_ok(sent, heard):
                    score -= EDGE_PENALTY
                if cands is None and score >= ACCEPT and not whisper_tail_ok(tmp, sent):
                    score = 0.0   # Whisper の切れ目なのに、文末が聞こえない。従来の方式の候補にゆずる
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
                score = _score(sent, heard)
                if not _edge_ok(sent, heard):
                    score -= EDGE_PENALTY
                if score > best[0]:
                    best = (score, best[1], heard)
            if best is not None and best[0] >= ACCEPT:
                break
        if best is not None and best[0] < ACCEPT:
            # 書き起こしが途中で切れただけ（文の前半は合っていて、音声の長さも文に見合う）なら採用する
            tn, hn = _norm(sent), _norm(best[2])
            exp_dur = span * (len(sent) + 1) / len(narration)
            if (len(hn) >= 20 and difflib.SequenceMatcher(None, tn[:len(hn)], hn, autojunk=False).ratio() >= 0.9
                    and best[1] - start >= 0.85 * exp_dur):
                best = (ACCEPT, best[1], best[2])
        tmp.unlink(missing_ok=True)
        if best is None or best[0] < ACCEPT:
            # 前の文の終わりが早すぎて、その最後の語が、この文の冒頭に混じって聞こえている（ep114: 「Seimei among them.」）。
            # 前の文の終わりを、次の切れ目まで後ろにずらして、この文をやり直す
            if i > 0 and i not in extended and best is not None and prev_tail_in_head(sents[i - 1], best[2]):
                later = sorted({c for cs in tiers for c in cs if c > start + 0.2})
                if later:
                    extended.add(i)
                    start = later[0]
                    _cut(scene_wav, starts[i - 1], start, paths[i - 1])
                    print(f"  （前の文の終わりを {start:.1f}s に延ばしました）")
                    continue
            print(f"切り出しが一致しません（一致度 {best[0] if best else 0:.2f}）: {sent}\n  聞こえた文: {best[2] if best else ''}")
            sys.exit(1)
        _cut(scene_wav, start, best[1], paths[i])
        starts.append(start)
        start = best[1]
        i += 1
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
