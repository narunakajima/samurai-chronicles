"""
sc_bgm_qa.py — BGM候補の音声QA（ボーカル・台詞混入チェック）

Gemini のマルチモーダル音声理解を使い、BGM候補にナレーションと競合する
人の声（歌詞・台詞・ナレーション・ささやき等）が含まれていないかを判定する。
sc_image_gen.py の画像QA（Gemini Vision）と同じ考え方で、音声版として実装。

使い方:
  python3 sc_bgm_qa.py --file <path.mp3>
  python3 sc_bgm_qa.py --dir <ディレクトリ>   # ディレクトリ内の *.mp3 を一括チェック
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from google import genai

import sc_gemini_model as gm

import os

API_KEY = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")
# モデル名は sc_gemini_model.py に集約（2026-11-09-025）

# ボーカル混入は大抵冒頭〜中盤で判別できるため、全尺ではなく先頭 QA_CLIP_SECONDS 秒
# のみをQAに送る（Gemini音声入力トークンを大幅削減する）。
QA_CLIP_SECONDS = 60

QA_PROMPT = (
    "Listen to this audio track. It will be used as instrumental background music (BGM) "
    "underneath a documentary narrator's voice, so any human voice in the track would "
    "clash with the narration.\n\n"
    "Determine whether the track contains ANY human vocals — sung lyrics, spoken dialogue, "
    "narration, whispering, chanting with words, or a vocal sample of any kind. "
    "Purely instrumental music (orchestral, strings, percussion, drones, wordless choir "
    "hums/oohs) should be marked has_vocals: false.\n\n"
    "Respond with ONLY a JSON object, no other text, in this exact format:\n"
    '{"has_vocals": true, "details": "brief description of the voice/lyrics heard"}\n'
    "or\n"
    '{"has_vocals": false, "details": "brief description of the instrumentation"}'
)


def _clip_audio_bytes(audio_path: Path, seconds: int = QA_CLIP_SECONDS) -> bytes:
    """先頭 seconds 秒だけを切り出したバイト列を返す。切り出しに失敗したら全尺を返す。"""
    suffix = audio_path.suffix or ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-t", str(seconds), "-c", "copy", tmp.name],
            capture_output=True,
        )
        if result.returncode == 0:
            clipped = Path(tmp.name).read_bytes()
            if clipped:
                return clipped
    return audio_path.read_bytes()


def qa_audio_with_gemini(client, audio_path: Path) -> dict:
    """音声ファイルをGemini に渡し、ボーカル・台詞混入の有無を判定する。"""
    try:
        data = _clip_audio_bytes(audio_path)
        mime_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        response = gm.generate_content(
            client,
            [
                QA_PROMPT,
                genai.types.Part.from_bytes(data=data, mime_type=mime_type),
            ],
            config=genai.types.GenerateContentConfig(
                thinking_config=genai.types.ThinkingConfig(thinking_budget=0)
            ),
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        # 応答が解釈できない場合（dictでない・has_vocalsが真偽値でない）は「合格」にしない（フェイルクローズ）
        if not isinstance(result, dict) or not isinstance(result.get("has_vocals"), bool):
            raise ValueError(f"応答を解釈できません: {text[:200]!r}")
        return {
            "file": audio_path.name,
            "status": "checked",
            "has_vocals": result["has_vocals"],
            "details": result.get("details", ""),
        }
    except Exception as e:
        # status="check_failed"（has_vocals=None）は「チェックできなかった」。
        # 「チェック済みでボーカルなし」(status=checked, has_vocals=False) とは別物で、合格扱いにしない。
        return {"file": audio_path.name, "status": "check_failed", "has_vocals": None,
                "details": f"QA失敗: {e}"}


def run(paths: list) -> list:
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)
    client = genai.Client(api_key=API_KEY)
    # QA判定より前段でモデルを解決する（モデル不存在がQAの例外処理に飲まれて「合格」扱いにならないように）
    try:
        print(f"  使用モデル: {gm.resolve_model(client)}")
    except gm.ModelUnavailable as e:
        print(f"❌ {e}")
        sys.exit(1)

    results = []
    for p in paths:
        print(f"  {p.name} 判定中... ", end="", flush=True)
        result = qa_audio_with_gemini(client, p)
        results.append(result)
        if result["has_vocals"] is None:
            print(f"❌ チェック不能（合格扱いにしません） — {result['details']}")
        elif result["has_vocals"]:
            print(f"❌ ボーカル/台詞あり — {result['details']}")
        else:
            print(f"✓ インストゥルメンタル — {result['details']}")
    return results


def main():
    parser = argparse.ArgumentParser(description="BGM候補の音声QA（ボーカル混入チェック）")
    parser.add_argument("--file", help="単一ファイルをチェック")
    parser.add_argument("--dir", help="ディレクトリ内の *.mp3 を一括チェック")
    args = parser.parse_args()

    if args.file:
        paths = [Path(args.file)]
    elif args.dir:
        paths = sorted(Path(args.dir).glob("*.mp3"))
        if not paths:
            print(f"❌ *.mp3 が見つかりません: {args.dir}")
            sys.exit(1)
    else:
        parser.error("--file または --dir を指定してください")
        return

    results = run(paths)
    flagged = [r for r in results if r["has_vocals"] is True]
    failed = [r for r in results if r["has_vocals"] is None]
    if flagged:
        print(f"\n⚠️  ボーカル/台詞混入の疑いがある候補: {len(flagged)}件")
        for r in flagged:
            print(f"  - {r['file']}: {r['details']}")
    if failed:
        print(f"\n❌ QAを実行できなかった候補（未チェック・合格ではない）: {len(failed)}件")
        for r in failed:
            print(f"  - {r['file']}: {r['details']}")
    if failed:
        sys.exit(2)  # 2 = チェック不能（1 = ボーカル検出）
    if flagged:
        sys.exit(1)
    print("\n✓ 全候補インストゥルメンタル確認済み")


if __name__ == "__main__":
    main()
