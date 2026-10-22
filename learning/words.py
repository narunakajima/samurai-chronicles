"""英語の各文（切り出した音声）から、単語ごとの話し始め・話し終わりの時刻を取る（動画の単語ハイライト用）。

手元の Whisper（openai-whisper、~/.cache/whisper のモデル）で単語の時刻を取り、台本の単語に当てはめる。
認識の聞き違いがあっても、台本の単語の並びに合わせ直すので、表示する単語は必ず台本どおりになる。
認識できなかった単語の時刻は、前後の単語の時刻から文字数の比率で補う。
"""
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
MODEL_NAME = "small"  # ~/.cache/whisper にある small.pt（large-v3-turbo より速い。単語の時刻の精度は十分）

_model = None


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout)


def _speech_onset(path: Path) -> float:
    """先頭の無音が終わる時刻（話し始め）。先頭が無音でなければ 0。"""
    log = subprocess.run(["ffmpeg", "-i", str(path), "-af", "silencedetect=n=-40dB:d=0.05", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    st = re.findall(r"silence_start: (-?[\d.]+)", log)
    en = re.findall(r"silence_end: ([\d.]+)", log)
    if st and en and float(st[0]) <= 0.02:
        return float(en[0])
    return 0.0


def word_times(clip: Path, sentence: str) -> list[dict]:
    """[{"w": 台本の単語, "s": 開始秒, "e": 終了秒}, ...]（clip の先頭からの秒）。結果は保存して使い回す。"""
    key = hashlib.sha1(f"{clip.name}|{sentence}|{MODEL_NAME}|v4".encode()).hexdigest()[:16]
    cache = CACHE_DIR / f"words_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    global _model
    if _model is None:
        import whisper
        _model = whisper.load_model(MODEL_NAME)
    r = _model.transcribe(str(clip), language="en", word_timestamps=True, initial_prompt=sentence,
                          fp16=False, condition_on_previous_text=False)
    heard = [(w["word"].strip(), float(w["start"]), float(w["end"])) for seg in r["segments"] for w in seg.get("words", [])]

    target = sentence.split()
    times: list = [None] * len(target)
    sm = difflib.SequenceMatcher(None, [_norm(w) for w in target], [_norm(h[0]) for h in heard], autojunk=False)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            times[a + k] = (heard[b + k][1], heard[b + k][2])

    # 話し始めより前の時刻や、前の単語より早い時刻は、認識の取り違えとみなして捨てる（あとで前後から補う）
    dur = _duration(clip)
    onset = _speech_onset(clip)
    # 文字数の比率から見積もった位置より大きく外れた時刻も、取り違えとみなす
    speech = max(dur - onset, 0.1)
    total_chars = sum(len(w) + 1 for w in target) or 1
    before = 0
    prev = onset - 0.05
    for k in range(len(times)):
        expected = onset + speech * before / total_chars
        before += len(target[k]) + 1
        if times[k] is None:
            continue
        if times[k][0] < prev or times[k][0] > dur or abs(times[k][0] - expected) > max(1.0, 0.25 * speech):
            times[k] = None
        else:
            prev = times[k][0]

    # 当てはまらなかった単語は、前後の分かっている時刻の間を、文字数の比率で分ける
    i = 0
    while i < len(target):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(target) and times[j] is None:
            j += 1
        lo = times[i - 1][1] if i > 0 else onset
        hi = times[j][0] if j < len(target) else dur
        span = max(hi - lo, 0.05 * (j - i))
        total = sum(len(w) for w in target[i:j]) or 1
        t = lo
        for k in range(i, j):
            d = span * len(target[k]) / total
            times[k] = (t, t + d)
            t += d
        i = j

    # Whisper は最初の単語の開始がずれやすい（早すぎる・遅すぎるの両方がある）ので、音声の話し始めに合わせる
    if times:
        s0, e0 = times[0]
        times[0] = (onset, max(e0, onset + 0.15))

    out = [{"w": w, "s": round(max(0.0, s), 3), "e": round(min(dur, e), 3)} for w, (s, e) in zip(target, times)]
    cache.write_text(json.dumps(out, ensure_ascii=False))
    return out
