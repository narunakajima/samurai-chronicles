"""Tokio の日本語解説音声を Gemini TTS で生成する（キャッシュ付き）。

SC 本編と同じモデル・声（narrator/tokio.json の Alnilam）を使い、英語本編と同じ人物に聞こえるようにする。
"""
import base64
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
import wave
from pathlib import Path

API_KEY = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")
TTS_MODEL = "gemini-3.8-flash-tts"
TTS_REST_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
VOICE_NAME = "Alnilam"
TEMPERATURE = 1.0
SAMPLE_RATE = 24000
CACHE_DIR = Path(__file__).parent / "cache"

# 2026-10-22: 英語本編と別人に聞こえるとの指摘を受け、本編の記者口調に寄せた指示に変更（ユーザーが試聴して選択）
STYLE_JA = (
    "You are Tokio Kamiya, a veteran field correspondent filing a calm, precise report from the scene. "
    "Speak Japanese in a composed, grounded, intimate reporter's tone: quietly authoritative with a dry edge. "
    "Same measured pace as a premium documentary narrator; do not over-dramatize, do not sound chatty or cheerful."
)


def _call(text: str, style: str) -> bytes:
    url = TTS_REST_URL.format(model=TTS_MODEL, key=API_KEY)
    body = {
        "contents": [{"role": "user", "parts": [{"text": text, "speech_metadata": {"style": style}}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE_NAME}}},
            "temperature": TEMPERATURE,
        },
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    for part in (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []:
        inline = part.get("inlineData")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise RuntimeError(f"レスポンスに音声データがありません: {str(data)[:300]}")


def to_pcm(data: bytes) -> bytes:
    """API の返す音声を、ヘッダーなしの PCM にそろえる。
    gemini-3.8-flash-tts はヘッダー付きの WAV を返すので、そのまま PCM として扱うと、先頭にノイズが、
    末尾にメタ情報の文字データが、音として混ざる（sc_tts_gen.py の RIFF 判定と同じ理由）。"""
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as w:
            return w.readframes(w.getnframes())
    return data


def write_wav(pcm: bytes, path: Path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


def tts(text: str, style: str = STYLE_JA, max_retries: int = 5) -> Path:
    """text を音声化して wav のパスを返す。同じ text+style はキャッシュを再利用する。"""
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha1((VOICE_NAME + style + text).encode("utf-8")).hexdigest()[:16]
    path = CACHE_DIR / f"{key}.wav"
    if path.exists():
        return path
    if not API_KEY:
        print("GEMINI_API_KEY_SC / GEMINI_API_KEY が未設定です")
        sys.exit(1)
    # 想定尺（1分あたり約300字）の2倍を超えたら繰り返し事故として再生成する
    max_sec = max(10.0, len(text) / 300 * 60 * 2)
    for attempt in range(1, max_retries + 1):
        try:
            pcm = to_pcm(_call(text, style))
            dur = len(pcm) / 2 / SAMPLE_RATE
            if dur <= max_sec:
                write_wav(pcm, path)
                return path
            print(f"  ⚠️ 長すぎる音声（{dur:.1f}s > {max_sec:.1f}s）、再生成")
        except Exception as e:
            print(f"  API エラー: {e}")
        time.sleep(2 ** attempt)
    print(f"TTS 失敗: {text[:40]}…")
    sys.exit(1)


if __name__ == "__main__":
    p = tts(sys.argv[1])
    with wave.open(str(p)) as w:
        sec = w.getnframes() / w.getframerate()
    print(p, f"{sec:.1f}s", f"{len(sys.argv[1]) / sec * 60:.0f}字/分")
