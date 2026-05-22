"""
sc_tts_gen.py — Samurai Chronicles 英語ナレーション生成スクリプト

使い方:
  python3 sc_tts_gen.py --episode ep001
  python3 sc_tts_gen.py --episode ep001 --scenes 1,3,5   # 特定シーンのみ再生成
  python3 sc_tts_gen.py --episode ep001 --takes 2        # 複数テイク

出力先: samurai-chronicles/audio/{episode_id}/
  S01.wav, S02.wav, ... S20.wav（またはテイク指定時: S01_take2.wav など）
"""

import argparse
import json
import os
import sys
import time
import wave
from pathlib import Path
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY", "")

TTS_MODEL = "gemini-3.1-flash-tts-preview"
VOICE_NAME = "Charon"   # 重厚・ドラマチックな男性英語ボイス
TEMPERATURE = 1.0
SAMPLE_RATE = 24000

BASE_DIR = Path(__file__).parent  # スクリプト・エピソードJSONの場所

# 生成素材の保存先（Google Drive）
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)

# ── ナレータープロファイル ─────────────────────────────
NARRATOR_STYLE = (
    "You are the narrator of a dramatic historical documentary series about samurai Japan. "
    "Speak in a deep, measured, cinematic tone — authoritative yet intimate. "
    "Pace yourself deliberately, with natural pauses between ideas. "
    "Convey weight, history, and human drama. Never rush. "
    "Tone: similar to a premium Netflix or BBC historical documentary."
)


def pcm_to_wav(pcm_data: bytes, output_path: Path, sample_rate: int = SAMPLE_RATE):
    """PCM バイト列を WAV ファイルとして保存する。"""
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def generate_take(client, narration_text: str, max_retries: int = 5) -> bytes:
    """1テイク生成して音声バイト列を返す（指数バックオフリトライ付き）。"""
    prompt = f"{NARRATOR_STYLE}\n\n{narration_text}"
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=VOICE_NAME
                )
            )
        ),
        temperature=TEMPERATURE,
    )
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=TTS_MODEL,
                contents=prompt,
                config=config,
            )
            candidate = response.candidates[0] if response.candidates else None
            parts = candidate.content.parts if (candidate and candidate.content) else None
            if parts:
                for part in parts:
                    if part.inline_data is not None:
                        return part.inline_data.data
        except Exception as e:
            print(f"  API エラー: {e}")
        if attempt < max_retries:
            wait = 2 ** attempt
            print(f"  (リトライ {attempt}/{max_retries - 1} / {wait}秒待機) ", end="", flush=True)
            time.sleep(wait)
    raise RuntimeError("音声データが返ってきませんでした（全リトライ失敗）")


def run(episode_id: str, scene_filter: list = None, takes: int = 1):
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    out_dir = DRIVE_BASE / episode_id / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes = ep["scenes"]
    if scene_filter:
        scenes = [s for s in scenes if s["scene_id"] in scene_filter]

    client = genai.Client(api_key=API_KEY)

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — ナレーション生成")
    print(f"  対象シーン: {len(scenes)} / {ep['total_scenes']}")
    print(f"  テイク数: {takes}  /  ボイス: {VOICE_NAME}")
    print(f"  出力先: {out_dir}")
    print(f"{'━'*60}\n")

    saved = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        narration = scene["narration"]
        for take in range(1, takes + 1):
            if takes == 1:
                out_file = out_dir / f"S{scene_id:02d}.wav"
            else:
                out_file = out_dir / f"S{scene_id:02d}_take{take}.wav"

            label = f"S{scene_id:02d}" + (f" テイク{take}" if takes > 1 else "")
            print(f"  {label} 生成中... ", end="", flush=True)
            try:
                audio_data = generate_take(client, narration)
                if audio_data[:4] == b"RIFF":
                    out_file.write_bytes(audio_data)
                else:
                    pcm_to_wav(audio_data, out_file)
                print(f"✓ {out_file.name}")
                saved.append(out_file)
            except Exception as e:
                print(f"⚠️  エラー: {e}")

            # テイク間インターバル
            if take < takes:
                time.sleep(3)

        # シーン間インターバル（レート制限対策）
        if scene_id < scenes[-1]["scene_id"]:
            time.sleep(2)

    print(f"\n{'━'*60}")
    print(f"  完了: {len(saved)} ファイル → {out_dir}")
    print(f"{'━'*60}\n")
    return saved


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles ナレーション生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    parser.add_argument("--scenes", default=None,
                        help="特定シーンのみ（例: 1,3,9）。省略時は全シーン")
    parser.add_argument("--takes", type=int, default=1, help="テイク数（デフォルト: 1）")
    args = parser.parse_args()

    scene_filter = None
    if args.scenes:
        scene_filter = [int(x.strip()) for x in args.scenes.split(",")]

    run(args.episode, scene_filter=scene_filter, takes=args.takes)


if __name__ == "__main__":
    cli()
