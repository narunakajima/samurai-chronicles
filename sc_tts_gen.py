"""
sc_tts_gen.py — Samurai Chronicles 英語ナレーション生成スクリプト

使い方:
  python3 sc_tts_gen.py --episode ep001
  python3 sc_tts_gen.py --episode ep001 --scenes 1,3,5   # 特定シーンのみ再生成
  python3 sc_tts_gen.py --episode ep001 --takes 2        # 複数テイク
  python3 sc_tts_gen.py --episode ep001 --force          # 既存ファイルも含め全シーン再生成

出力先: samurai-chronicles/audio/{episode_id}/
  S01.wav, S02.wav, ... S20.wav（またはテイク指定時: S01_take2.wav など）

生成済みならスキップ（2026-09-04〜、sc_image_gen.pyと同じ考え方）:
  --scenes未指定のフル実行では、既に音声が存在するシーンは再生成しない。
  全シーンを強制的に作り直したい場合は --force。
"""

import argparse
import io
import json
import os
import re
import sys
import time
import wave
from pathlib import Path
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")

TTS_MODEL = "gemini-3.1-flash-tts-preview"
QA_MODEL = "gemini-3.7-flash"  # ナレーション音声が台本通りか判定する用（sc_image_gen.pyのQA_MODELと同じ考え方）
VOICE_NAME = "Charon"   # 重厚・ドラマチックな男性英語ボイス
TEMPERATURE = 1.0
SAMPLE_RATE = 24000

# ── ナレーション繰り返し検知 ─────────────────────────────────
# Gemini TTS が稀にナレーション全体を2回繰り返した音声を返すことがある。
# 語数から推定した尺の DUP_RATIO_THRESHOLD 倍を超えたら「繰り返しの疑い」として再生成する。
DUP_RATIO_THRESHOLD = 1.6
MAIN_EXPECTED_WPM = 85.0     # 本編ナレーション（insight等の低速シーンも考慮した下限的な値）
TRAILER_EXPECTED_WPM = 90.0   # teaser / shorts（実測: Gemini TTS は ~80-90 WPM で読む）

import subprocess  # noqa: E402（silenceremove用）

BASE_DIR = Path(__file__).parent  # スクリプト・エピソードJSONの場所

# 生成素材の保存先（Google Drive）
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)

# ── ナレータープロファイル（本編用・デフォルト） ─────────────────────────────
NARRATOR_STYLE = (
    "You are the narrator of a dramatic historical documentary series about samurai Japan. "
    "Speak in a deep, measured, cinematic tone — authoritative yet intimate. "
    "Pace yourself deliberately, with natural pauses between ideas. "
    "Convey weight, history, and human drama. Never rush. "
    "Tone: similar to a premium Netflix or BBC historical documentary."
)

# ── シーンタイプ別スタイル（デフォルトを上書き） ───────────────
# 各エントリはデフォルトの NARRATOR_STYLE に追記するかたちで使用
SCENE_TYPE_ADDENDUM = {
    "hook": (
        " For this opening hook: speak with sharp urgency and intrigue. "
        "Drop the listener straight into the tension. No warm-up. "
        "Create an immediate sense of 'I must keep watching.'"
    ),
    "climax": (
        " For this climax scene: increase your intensity significantly. "
        "Speak faster, with barely contained urgency — this is the moment everything breaks. "
        "Let the gravity of the event come through in every word."
    ),
    "falling_action": (
        " For this falling action scene: slow slightly from the climax. "
        "Heavy, grave, somber. The dust is settling. Something has changed forever."
    ),
    "rising_action": (
        " For this rising action scene: build steady tension. "
        "Each sentence increases the stakes. A sense of inevitability."
    ),
    "insight": (
        " For this insight scene: shift to a reflective, thoughtful register. "
        "Slower and more deliberate — a historian pausing to consider meaning. "
        "Contemplative yet authoritative."
    ),
    "teaser": (
        " For this teaser: cinematic movie trailer style. "
        "Fast, punchy, intense — drop the audience into the drama immediately. "
        "Leave them needing to know what happens next."
    ),
    "outro": (
        " For this outro: warm, inviting, forward-looking. "
        "Slightly lighter tone — the story is complete, but a new one awaits."
    ),
}


def audio_duration_sec(data: bytes, sample_rate: int = SAMPLE_RATE) -> float:
    """音声バイト列（WAVまたはPCM raw）の長さを秒で返す。"""
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as wf:
            return wf.getnframes() / float(wf.getframerate())
    return len(data) / 2 / float(sample_rate)


def pcm_to_wav(pcm_data: bytes, output_path: Path, sample_rate: int = SAMPLE_RATE):
    """PCM バイト列を WAV ファイルとして保存する。"""
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def _to_wav_bytes(audio_data: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """WAV/PCMいずれのバイト列でも、QA用にWAVバイト列へ正規化する。"""
    if audio_data[:4] == b"RIFF":
        return audio_data
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)
    return buf.getvalue()


def qa_narration_with_gemini(client, audio_data: bytes, script_text: str) -> dict:
    """生成されたナレーション音声が台本通りに発話されているかをGeminiに判定させる。
    Gemini TTSは稀に台本の一部を省略・改変したり、途中で発話が途切れたりすることが
    あるため、人間が毎回聴いて確認する前段のフィルタとして自動チェックする
    （sc_bgm_qa.pyの音声QAと同じ、Geminiのマルチモーダル音声理解を使う考え方）。"""
    try:
        wav_bytes = _to_wav_bytes(audio_data)
        qa_prompt = (
            "Listen to this narration audio and compare it against the intended script below.\n\n"
            "Check for these issues:\n"
            "- SKIPPED: one or more sentences or phrases from the script are missing from the audio\n"
            "- ALTERED: the spoken words deviate significantly from the script — not just natural "
            "reading variation (pauses, emphasis), but substituted, garbled, or materially different wording\n"
            "- REPEATED: any part of the script is spoken more than once\n"
            "- CUTOFF: the audio ends abruptly mid-sentence or mid-word instead of completing the script\n\n"
            f"Script:\n{script_text}\n\n"
            "Respond with ONLY a JSON object, no other text, in this exact format:\n"
            '{"ok": true, "issues": []}\n'
            "or\n"
            '{"ok": false, "issues": ["ISSUE_TYPE: brief description", ...]}'
        )
        response = client.models.generate_content(
            model=QA_MODEL,
            contents=[
                qa_prompt,
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        return {"ok": bool(result.get("ok", True)), "issues": result.get("issues", [])}
    except Exception as e:
        # QA自体が失敗した場合はサイレントにOK扱いせず、issueとして扱い
        # 既存のリトライ機構に乗せる（API障害等を「問題なし」と誤認しないため）。
        return {"ok": False, "issues": [f"QA_ERROR: {e}"]}


def build_prompt(narration_text: str, scene_type: str = "") -> str:
    """シーンタイプに応じたスタイル指示 + ナレーションテキストでプロンプトを構築する。"""
    style = NARRATOR_STYLE
    if scene_type and scene_type in SCENE_TYPE_ADDENDUM:
        style = NARRATOR_STYLE + SCENE_TYPE_ADDENDUM[scene_type]
    return f"{style}\n\n{narration_text}"


def generate_take(client, narration_text: str, max_retries: int = 5,
                  scene_type: str = "", expected_wpm: float = MAIN_EXPECTED_WPM,
                  dup_check_text: str = None) -> bytes:
    """1テイク生成して音声バイト列を返す（指数バックオフリトライ付き）。

    語数から推定した尺の DUP_RATIO_THRESHOLD 倍を超える音声が返った場合は
    「ナレーション繰り返し」の疑いとして再生成する。
    """
    prompt = build_prompt(narration_text, scene_type)
    word_count = len((dup_check_text or narration_text).split())
    max_dur = word_count / expected_wpm * 60 * DUP_RATIO_THRESHOLD
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
    last_audio_data = None
    last_fail_reason = ""
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
                        audio_data = part.inline_data.data
                        actual_dur = audio_duration_sec(audio_data)
                        if actual_dur > max_dur:
                            print(f"  ⚠️ 繰り返しの疑い（{actual_dur:.1f}s > 想定上限{max_dur:.1f}s） ", end="", flush=True)
                            last_audio_data = audio_data
                            last_fail_reason = f"繰り返しの疑い（想定上限{max_dur:.1f}s超）"
                            break
                        qa = qa_narration_with_gemini(client, audio_data, dup_check_text or narration_text)
                        if not qa["ok"]:
                            print(f"  ⚠️ 台本不一致の疑い（{'; '.join(qa['issues'])}） ", end="", flush=True)
                            last_audio_data = audio_data
                            last_fail_reason = f"台本不一致の疑い（{'; '.join(qa['issues'])}）"
                            break
                        return audio_data
        except Exception as e:
            print(f"  API エラー: {e}")
        if attempt < max_retries:
            wait = 2 ** attempt
            print(f"(リトライ {attempt}/{max_retries - 1} / {wait}秒待機) ", end="", flush=True)
            time.sleep(wait)
    if last_audio_data is not None:
        raise RuntimeError(
            f"全{max_retries}回のテイクが{last_fail_reason}のままでした。再実行してください。"
        )
    raise RuntimeError("音声データが返ってきませんでした（全リトライ失敗）")


def remove_silence(src: Path, dst: Path):
    """無音区間を除去する（Shorts・本編teaser共用）。
    -40dB / 0.15s: 本当の無音のみ除去、息継ぎや文末の間は保持。
    末尾に 0.3s の無音を付加してクロスフェード余白を確保する。
    """
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src),
        "-af", (
            "silenceremove=stop_periods=-1"
            ":stop_duration=0.15"
            ":stop_threshold=-40dB"
            ",apad=pad_dur=0.3"
        ),
        str(dst),
    ], capture_output=True)


def run_teaser(episode_id: str):
    """トレイラー風イントロナレーション（teaser_narration）を生成。
    出力: audio/{episode_id}/S00_teaser.wav（無音除去済み）
    """
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません"); sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}"); sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    teaser_narration = ep.get("teaser_narration", "")
    if not teaser_narration:
        print(f"❌ 'teaser_narration' フィールドがありません: {ep_json}"); sys.exit(1)

    out_dir = DRIVE_BASE / episode_id / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=API_KEY)

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — Teaser ナレーション生成（トレイラースタイル）")
    print(f"  出力先: {out_dir}/S00_teaser.wav")
    print(f"{'━'*60}\n")

    import tempfile as _tmpmod
    with _tmpmod.TemporaryDirectory() as _tmp:
        raw_wav = Path(_tmp) / "raw.wav"
        out_file = out_dir / "S00_teaser.wav"

        print(f"  TTS生成中... ", end="", flush=True)
        audio_data = generate_take(client, teaser_narration, scene_type="teaser",
                                    expected_wpm=TRAILER_EXPECTED_WPM)
        if audio_data[:4] == b"RIFF":
            raw_wav.write_bytes(audio_data)
        else:
            pcm_to_wav(audio_data, raw_wav)
        print("✓（raw）")

        print(f"  無音除去中... ", end="", flush=True)
        remove_silence(raw_wav, out_file)
        print("✓")

    print(f"\n  ✓ 完了: {out_file.name}")
    print(f"{'━'*60}\n")


def run_shorts(episode_id: str):
    """Shorts専用ナレーション（shorts_narration フィールド）をトレイラースタイルで生成。
    出力: audio/{episode_id}/S00_shorts.wav
    """
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    shorts_narration = ep.get("shorts_narration", "")
    if not shorts_narration:
        print(f"❌ エピソードJSONに 'shorts_narration' フィールドがありません: {ep_json}")
        sys.exit(1)

    out_dir = DRIVE_BASE / episode_id / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=API_KEY)

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — Shorts ナレーション生成（トレイラースタイル）")
    print(f"  出力先: {out_dir}/S00_shorts.wav")
    print(f"{'━'*60}\n")

    import tempfile as _tmpmod
    with _tmpmod.TemporaryDirectory() as _tmp:
        raw_wav = Path(_tmp) / "raw.wav"
        out_file = out_dir / "S00_shorts.wav"

        print(f"  TTS生成中... ", end="", flush=True)
        audio_data = generate_take(client, shorts_narration, scene_type="teaser",
                                    expected_wpm=TRAILER_EXPECTED_WPM,
                                    dup_check_text=shorts_narration)
        if audio_data[:4] == b"RIFF":
            raw_wav.write_bytes(audio_data)
        else:
            pcm_to_wav(audio_data, raw_wav)
        print("✓（raw）")

        print(f"  無音除去中... ", end="", flush=True)
        remove_silence(raw_wav, out_file)
        print("✓")

    print(f"\n  ✓ 完了: {out_file.name}")
    print(f"{'━'*60}\n")


def run(episode_id: str, scene_filter: list = None, takes: int = 1, force: bool = False):
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

    # 「生成済みならスキップ」（2026-09-04〜）: --scenes未指定のフル実行では、
    # 既に音声が存在するシーンは再生成しない（sc_image_gen.pyと同じ考え方）。
    skip_existing = scene_filter is None and not force
    skipped_count = 0

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

            if skip_existing and out_file.exists():
                print(f"  {label} … 既存ファイルをスキップ")
                saved.append(out_file)
                skipped_count += 1
                continue

            scene_type = scene.get("type", "")
            print(f"  {label} [{scene_type}] 生成中... ", end="", flush=True)
            try:
                audio_data = generate_take(client, narration, scene_type=scene_type)
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
    skip_note = f"（うちスキップ{skipped_count}件）" if skipped_count else ""
    print(f"  完了: {len(saved)} ファイル{skip_note} → {out_dir}")
    print(f"{'━'*60}\n")
    return saved


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles ナレーション生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    parser.add_argument("--scenes", default=None,
                        help="特定シーンのみ（例: 1,3,9）。省略時は全シーン")
    parser.add_argument("--takes", type=int, default=1, help="テイク数（デフォルト: 1）")
    parser.add_argument("--shorts", action="store_true",
                        help="Shorts専用ナレーション（shorts_narration）をトレイラースタイルで生成")
    parser.add_argument("--teaser", action="store_true",
                        help="本編トレイラーイントロ（teaser_narration）を生成 → S00_teaser.wav")
    parser.add_argument("--force", action="store_true",
                        help="--scenes未指定のフル実行で、既存ファイルがあっても全シーン再生成する（デフォルトは既存ファイルをスキップ）")
    args = parser.parse_args()

    if args.teaser:
        run_teaser(args.episode)
        return

    if args.shorts:
        run_shorts(args.episode)
        return

    scene_filter = None
    if args.scenes:
        scene_filter = [int(x.strip()) for x in args.scenes.split(",")]

    run(args.episode, scene_filter=scene_filter, takes=args.takes, force=args.force)


if __name__ == "__main__":
    cli()
