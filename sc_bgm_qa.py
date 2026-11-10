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

# 全尺を送るとトークンが大きいので、曲の先頭・中盤・終盤から QA_SEGMENT_SECONDS 秒ずつ抜き出してつなぐ
# （2026-11-11: 先頭60秒だけでは、冒頭はオーケストラでも全尺ではシンセが大半という曲を見逃した。
#  ボーカルも終盤にだけ入る曲がありうる）。曲が QA_FULL_MAX_SECONDS 秒以下なら全尺をそのまま送る。
QA_SEGMENT_SECONDS = 30
QA_SEGMENT_STARTS = (0.0, 0.45, 0.9)   # 各区間の開始位置（曲の長さに対する割合。終盤は曲の終わりを超えないよう切り詰める）
QA_FULL_MAX_SECONDS = 100
QA_ATTEMPTS = 3   # 応答を JSON として読めないときの試行回数（1回目は思考なし、2回目以降は思考あり。2026-11-11）

QA_PROMPT = (
    "Listen to this audio track. It will be used as instrumental background music (BGM) "
    "underneath a documentary narrator's voice, so any human voice in the track would "
    "clash with the narration.\n\n"
    "The audio may be several excerpts joined together (start, middle and end of one track); judge the track as a whole, "
    "and in the details also note whether the instrumentation (orchestral / synthesizer / other) is consistent across the excerpts.\n\n"
    "Determine whether the track contains ANY human vocals — sung lyrics, spoken dialogue, "
    "narration, whispering, chanting with words, or a vocal sample of any kind. "
    "Purely instrumental music (orchestral, strings, percussion, drones, wordless choir "
    "hums/oohs) should be marked has_vocals: false.\n\n"
    "Respond with ONLY a JSON object, no other text, in this exact format:\n"
    '{"has_vocals": true, "details": "brief description of the voice/lyrics heard"}\n'
    "or\n"
    '{"has_vocals": false, "details": "brief description of the instrumentation"}'
)


def _duration(audio_path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _clip_audio_bytes(audio_path: Path) -> bytes:
    """QA に送る音声のバイト列を返す。短い曲は全尺、長い曲は先頭・中盤・終盤の各区間をつないだもの。
    切り出しに失敗したら全尺を返す（トークンは増えるが、見逃さない側に倒す）。"""
    dur = _duration(audio_path)
    if dur <= QA_FULL_MAX_SECONDS:
        return audio_path.read_bytes()
    segs = []
    for r in QA_SEGMENT_STARTS:
        st = min(dur * r, max(0.0, dur - QA_SEGMENT_SECONDS))
        segs.append(st)
    parts = "".join(f"[0:a]atrim=start={st:.2f}:duration={QA_SEGMENT_SECONDS},asetpts=PTS-STARTPTS[a{i}];"
                    for i, st in enumerate(segs))
    fc = parts + "".join(f"[a{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1[out]"
    with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
        result = subprocess.run(["ffmpeg", "-y", "-i", str(audio_path), "-filter_complex", fc, "-map", "[out]",
                                 "-c:a", "libmp3lame", "-b:a", "128k", tmp.name], capture_output=True)
        if result.returncode == 0:
            clipped = Path(tmp.name).read_bytes()
            if clipped:
                return clipped
    return audio_path.read_bytes()


def _parse_qa(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    result = json.loads(text)
    # 応答が解釈できない場合（dictでない・has_vocalsが真偽値でない）は「合格」にしない（フェイルクローズ）
    if not isinstance(result, dict) or not isinstance(result.get("has_vocals"), bool):
        raise ValueError(f"応答を解釈できません: {text[:200]!r}")
    return result


def qa_audio_with_gemini(client, audio_path: Path) -> dict:
    """音声ファイルをGemini に渡し、ボーカル・台詞混入の有無を判定する。
    応答を読めなければ再試行する（thinking_budget=0 だと JSON を返さないことが多いため、2回目以降は思考を有効にする）。"""
    last_err = None
    try:
        data = _clip_audio_bytes(audio_path)
        mime_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        for attempt in range(QA_ATTEMPTS):
            try:
                cfg = (genai.types.GenerateContentConfig(thinking_config=genai.types.ThinkingConfig(thinking_budget=0))
                       if attempt == 0 else genai.types.GenerateContentConfig())
                response = gm.generate_content(
                    client,
                    [QA_PROMPT, genai.types.Part.from_bytes(data=data, mime_type=mime_type)],
                    config=cfg,
                )
                result = _parse_qa(response.text)
                return {
                    "file": audio_path.name,
                    "status": "checked",
                    "has_vocals": result["has_vocals"],
                    "details": result.get("details", ""),
                }
            except (json.JSONDecodeError, ValueError, AttributeError) as e:   # 応答が読めない → 再試行
                last_err = e
        raise last_err
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
