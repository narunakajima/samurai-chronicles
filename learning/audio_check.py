"""音声ファイルを Gemini に聴かせて質問する（日本語の自然さ・英語の発音・切り出しの確認用）。"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

from tts_ja import API_KEY

MODEL = "gemini-flash-latest"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


def ask(audio_path: Path, question: str) -> str:
    data = base64.b64encode(Path(audio_path).read_bytes()).decode()
    body = {"contents": [{"role": "user", "parts": [
        {"inlineData": {"mimeType": "audio/wav", "data": data}},
        {"text": question},
    ]}]}
    req = urllib.request.Request(URL.format(model=MODEL, key=API_KEY), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read())
    return out["candidates"][0]["content"]["parts"][0]["text"]


def check_japanese(audio_path: Path, script: str) -> dict:
    """日本語の解説音声が台本どおりに読まれているかを判定する。{"ok": bool, "issues": [...]}"""
    q = ("以下は日本語ナレーションの台本です。音声がこの台本どおりに読まれているか判定してください。\n"
         "問題にするのは、読み飛ばし・繰り返し・言い間違い・明らかな漢字の誤読・途中で別の言語の訛りになる箇所だけです。"
         "句読点の間の取り方や、ひらがなと漢字の表記の違いは問題にしません。\n"
         '出力はJSONのみ: {"ok": true/false, "issues": ["具体的な問題", ...]}\n\n台本:\n' + script)
    text = ask(audio_path, q).strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "issues": [f"判定結果を読めません: {text[:200]}"]}


if __name__ == "__main__":
    print(ask(Path(sys.argv[1]), sys.argv[2]))
