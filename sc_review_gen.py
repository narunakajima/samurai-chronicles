"""
sc_review_gen.py — Samurai Chronicles 制作確認書生成スクリプト

動画生成の前にユーザーが内容を確認するためのドキュメントを作成する。
確認項目: エピソード概要 / 各シーンのナレーション日本語訳 / ファクトチェック結果

使い方:
  python3 sc_review_gen.py --episode ep001
  → ~/Desktop/ep001_制作確認書.txt を生成

ユーザーがOKを出したら動画生成（sc_video_gen.py）に進む。
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")
TEXT_MODEL = "gemini-2.5-flash"

BASE_DIR = Path(__file__).parent
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)


def translate_to_japanese(client, text: str) -> str:
    """英語ナレーションを日本語に翻訳する。"""
    prompt = (
        "以下の英語のナレーションを自然な日本語に翻訳してください。"
        "歴史ドキュメンタリーのナレーションとして適切なトーンにしてください。"
        "翻訳文のみ返してください。\n\n"
        f"{text}"
    )
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
    )
    return response.text.strip()


def factcheck_episode(client, ep: dict) -> str:
    """エピソード全体のファクトチェックを実行する。"""
    # 全ナレーションをまとめてファクトチェック
    all_narration = "\n".join(
        f"S{s['scene_id']:02d}: {s['narration']}" for s in ep["scenes"]
    )
    prompt = (
        f"以下は「{ep['episode_title']}」というYouTube歴史ドキュメンタリーの全ナレーションです。\n\n"
        f"{all_narration}\n\n"
        "このナレーションに含まれる歴史的事実をファクトチェックしてください。\n"
        "以下の形式で日本語で回答してください:\n\n"
        "【✅ 確認済み・正確な情報】\n"
        "（箇条書きで確認できた事実を列挙）\n\n"
        "【⚠️ 注意・議論あり】\n"
        "（諸説ある点、要注記の点を箇条書きで）\n\n"
        "【❌ 誤り・修正が必要】\n"
        "（明確な誤りがあれば指摘。なければ「特になし」）\n\n"
        "【総評】\n"
        "（全体的な歴史的正確性についての一言コメント）"
    )
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
    )
    return response.text.strip()


def run(episode_id: str):
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    audio_dir = DRIVE_BASE / episode_id / "audio"
    bgm_file = audio_dir / f"{episode_id}-BGM.mp3"

    client = genai.Client(api_key=API_KEY)

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — 制作確認書生成")
    print(f"{'━'*60}\n")

    # ── 1. ファクトチェック ────────────────────────────
    print("  ファクトチェック実行中... ", end="", flush=True)
    factcheck_result = factcheck_episode(client, ep)
    print("✓")

    # ── 2. 各シーン翻訳 ───────────────────────────────
    print(f"  各シーンの翻訳（{len(ep['scenes'])}シーン）...")
    scene_translations = []
    for scene in ep["scenes"]:
        sid = scene["scene_id"]
        print(f"    S{sid:02d} 翻訳中... ", end="", flush=True)
        translation = translate_to_japanese(client, scene["narration"])
        scene_translations.append(translation)
        print("✓")

    # ── 3. ドキュメント組み立て ────────────────────────
    today = date.today().strftime("%Y-%m-%d")
    bgm_status = f"✅ {bgm_file.name}" if bgm_file.exists() else "❌ 未選択"

    lines = []
    lines.append("=" * 64)
    lines.append(f"  Samurai Chronicles {episode_id.upper()} 制作確認書")
    lines.append(f"  生成日: {today}")
    lines.append("=" * 64)
    lines.append("")

    # エピソード概要
    lines.append("【エピソード概要】")
    lines.append("-" * 40)
    lines.append(f"エピソードID  : {ep['episode_id']}")
    lines.append(f"タイトル      : {ep['episode_title']}")
    lines.append(f"YouTube タイトル: {ep['youtube_title']}")
    lines.append(f"総シーン数    : {ep['total_scenes']}")
    lines.append(f"Shorts シーン : S{ep.get('shorts_highlight_scene', '?'):02d}")
    lines.append(f"BGM           : {bgm_status}")
    lines.append("")
    lines.append("▼ YouTube 説明文（英語）")
    lines.append(ep.get("youtube_description", "（なし）"))
    lines.append("")
    lines.append("▼ タグ")
    lines.append(", ".join(ep.get("youtube_tags", [])))
    lines.append("")

    # 各シーンのナレーション
    lines.append("=" * 64)
    lines.append("【各シーンのナレーション】")
    lines.append("=" * 64)
    lines.append("")

    for i, scene in enumerate(ep["scenes"]):
        sid = scene["scene_id"]
        stype = scene.get("type", "")
        char = scene.get("character_ref") or "—"
        dur = scene.get("duration_seconds", 20)
        lines.append(f"▶ S{sid:02d}  [{stype}]  キャラクター: {char}  想定尺: {dur}秒")
        lines.append("")
        lines.append("  【EN】")
        for sent in scene["narration"].split(". "):
            if sent.strip():
                lines.append(f"  {sent.strip()}{'.' if not sent.strip().endswith('.') else ''}")
        lines.append("")
        lines.append("  【JA】")
        for sent_ja in scene_translations[i].split("。"):
            if sent_ja.strip():
                lines.append(f"  {sent_ja.strip()}。")
        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    # ファクトチェック
    lines.append("=" * 64)
    lines.append("【ファクトチェック結果】")
    lines.append("=" * 64)
    lines.append("")
    lines.append(factcheck_result)
    lines.append("")

    # 承認欄
    lines.append("=" * 64)
    lines.append("【確認・承認】")
    lines.append("-" * 40)
    lines.append("□ 内容確認完了")
    lines.append("□ ファクトチェック問題なし")
    lines.append("□ BGM選択完了")
    lines.append("□ 動画生成GO")
    lines.append("")
    lines.append("備考:")
    lines.append("")
    lines.append("=" * 64)

    # ── 4. デスクトップ＆エピソードフォルダに保存 ──────────
    content = "\n".join(lines)
    filename = f"{episode_id}_制作確認書.txt"

    output_path = Path.home() / "Desktop" / filename
    output_path.write_text(content, encoding="utf-8")

    drive_path = DRIVE_BASE / episode_id / filename
    drive_path.parent.mkdir(parents=True, exist_ok=True)
    drive_path.write_text(content, encoding="utf-8")

    print(f"\n{'━'*60}")
    print(f"  ✓ 完成: {output_path}")
    print(f"  ✓ 保存: {drive_path}")
    print(f"{'━'*60}\n")
    return output_path


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles 制作確認書生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    args = parser.parse_args()
    run(args.episode)


if __name__ == "__main__":
    cli()
