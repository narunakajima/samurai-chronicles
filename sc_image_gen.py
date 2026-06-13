"""
sc_image_gen.py — Samurai Chronicles 静止画生成スクリプト

使い方:
  python3 sc_image_gen.py --episode ep001
  python3 sc_image_gen.py --episode ep001 --scenes 1,3,9   # 特定シーンのみ再生成

出力先: samurai-chronicles/images/{episode_id}/
  S01.png, S02.png, ... S20.png

キャラクター参照:
  ep001.json の各シーンに "character_ref": "musashi" がある場合、
  characters/musashi.txt のキャラクター設定が BASE_CONTEXT に追加される。
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")

MODEL = "gemini-3.1-flash-image-preview"
QA_MODEL = "gemini-2.0-flash"

BASE_DIR = Path(__file__).parent  # スクリプト・エピソードJSONの場所

# 生成素材の保存先（Google Drive）
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)

# ── ベースコンテキスト（全シーン共通） ───────────────────
BASE_CONTEXT = (
    "Modern cinematic concept art style. High detail, realistic proportions. "
    "Dramatic lighting with deep shadows and strong directional light. "
    "Film production illustration quality — similar to high-end historical film concept art. "
    "Color palette: deep blue-grey, warm gold, mist white, shadow black. "
    "Atmospheric depth: foreground sharp, background softened by mist or distance. "
    "Mood: epic, weighty, emotionally resonant, historically grounded. "
    "No text, no watermarks, no modern elements, no anachronisms. "
    "All human figures are East Asian / Japanese in appearance. "
    "Period-accurate Edo/Sengoku era attire: kimono, samurai armor, period weapons only."
)

# ── キャラクター参照定義 ──────────────────────────────────
# characters/ フォルダに {name}.txt があればそこから読む。なければここのデフォルトを使用。
CHARACTER_DEFAULTS = {
    "musashi": (
        "Miyamoto Musashi: lean, intense male samurai in his late 20s. "
        "Wild, unkempt hair. Simple dark worn kimono. Two swords (daisho). "
        "Sharp, perceptive eyes. Weathered face. No armor — raw and primal presence."
    ),
    "kojiro": (
        "Sasaki Kojiro: refined, aristocratic male swordsman in his late 20s. "
        "Elegant appearance, well-groomed. Blue formal kimono or light armor. "
        "Handsome face, composed expression. Carries an exceptionally long nodachi (longsword). "
        "Polished, controlled, noble bearing."
    ),
}


def load_character_ref(name: str) -> str:
    """キャラクター参照テキストをロードする。ファイルがあればファイル優先。"""
    if not name:
        return ""
    txt_path = BASE_DIR / "characters" / f"{name}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8").strip()
    return CHARACTER_DEFAULTS.get(name, "")


def generate_one_image_portrait(client, scene_prompt: str, character_ref: str, output_path: Path) -> bool:
    """Shorts用縦長(9:16)画像を生成する。同モデル・縦型プロンプト指定。"""
    parts = [
        "Cinematic vertical short film still, 9:16 format. "
        "Subject centered and prominent in frame. Composed for portrait mobile viewing. "
        + BASE_CONTEXT,
    ]
    if character_ref:
        parts.append(f"Character reference: {character_ref}")
    parts.append(f"Scene: {scene_prompt}")
    full_prompt = "\n\n".join(parts)

    response = client.models.generate_content(
        model=MODEL,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            output_path.write_bytes(part.inline_data.data)
            return True
    return False


def generate_one_image(client, scene_prompt: str, character_ref: str, output_path: Path) -> bool:
    """1シーン1枚生成して output_path に保存。成功すれば True を返す。"""
    parts = [BASE_CONTEXT]
    if character_ref:
        parts.append(f"Character reference: {character_ref}")
    parts.append(f"Scene: {scene_prompt}")
    full_prompt = "\n\n".join(parts)

    response = client.models.generate_content(
        model=MODEL,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            output_path.write_bytes(part.inline_data.data)
            return True
    return False


def qa_image_with_gemini(client, image_path: str, image_prompt: str, scene_id: int) -> dict:
    """生成画像をGemini Visionで自動チェックする。問題があれば issues に格納する。"""
    try:
        image = Image.open(image_path)
        qa_prompt = (
            "You are a quality-control reviewer for AI-generated historical concept art images "
            "used in a samurai history video series.\n\n"
            "Check the image against the intended scene description for these issue types:\n"
            "- MISMATCH: the image does not match the scene description (wrong subject, action, or setting)\n"
            "- DISTORTION: anatomical errors, malformed faces/hands/bodies, broken or warped objects\n"
            "- TEXT: any readable text, captions, watermarks, or logos appear in the image\n"
            "- ARCHITECTURE: anachronistic or era-incorrect architecture, objects, or clothing for Edo/Sengoku Japan\n\n"
            f"Scene description: {image_prompt}\n\n"
            "Respond with ONLY a JSON object, no other text, in this exact format:\n"
            '{"ok": true, "issues": []}\n'
            "or\n"
            '{"ok": false, "issues": ["ISSUE_TYPE: brief description", ...]}'
        )

        response = client.models.generate_content(
            model=QA_MODEL,
            contents=[qa_prompt, image],
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        return {
            "scene_id": scene_id,
            "ok": bool(result.get("ok", True)),
            "issues": result.get("issues", []),
        }
    except Exception:
        return {"scene_id": scene_id, "ok": True, "issues": []}


def run(episode_id: str, scene_filter: list = None, shorts: bool = False):
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    if shorts:
        # Shorts用シーンを内容重視で選択（8枚）
        # 1. shorts_highlight_scene を必ず含む
        # 2. 劇的なシーンタイプを優先
        # 3. 残りを等間隔で補完
        all_scenes = ep["scenes"]
        highlight_id = ep.get("shorts_highlight_scene")
        selected_ids = set()

        # highlight シーンを確保
        if highlight_id:
            selected_ids.add(highlight_id)

        # タイプ優先度順に追加
        priority_types = ["hook", "climax", "teaser", "insight", "falling_action", "outro", "rising_action", "setup"]
        for ptype in priority_types:
            if len(selected_ids) >= 8:
                break
            for s in all_scenes:
                if len(selected_ids) >= 8:
                    break
                if s["type"] == ptype and s["scene_id"] not in selected_ids:
                    selected_ids.add(s["scene_id"])

        # それでも8枚に足りない場合は等間隔で補完
        if len(selected_ids) < 8:
            n_fill = 8 - len(selected_ids)
            remaining = [s for s in all_scenes if s["scene_id"] not in selected_ids]
            step = max(1, len(remaining) // n_fill)
            for i in range(0, len(remaining), step):
                if len(selected_ids) >= 8:
                    break
                selected_ids.add(remaining[i]["scene_id"])

        # scene_id 順にソート
        scenes = sorted([s for s in all_scenes if s["scene_id"] in selected_ids], key=lambda s: s["scene_id"])
        out_dir = DRIVE_BASE / episode_id / "images_shorts"
        gen_func = generate_one_image_portrait
        label = "Shorts縦長(9:16)"
        # 再生成時に旧ファイルが残らないよう既存PNGをクリア
        if out_dir.exists():
            for f in out_dir.glob("S*.png"):
                f.unlink()
    else:
        scenes = ep["scenes"]
        if scene_filter:
            scenes = [s for s in scenes if s["scene_id"] in scene_filter]
        out_dir = DRIVE_BASE / episode_id / "images"
        gen_func = generate_one_image
        label = "横長(16:9)"

    out_dir.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=API_KEY)

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — 静止画生成 [{label}]")
    print(f"  対象シーン: {len(scenes)}")
    print(f"  出力先: {out_dir}")
    print(f"{'━'*60}\n")

    saved = []
    qa_results = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        prompt = scene["image_prompt"]
        char_ref_name = scene.get("character_ref")
        char_ref = load_character_ref(char_ref_name)
        out_file = out_dir / f"S{scene_id:02d}.png"

        ref_label = f" [{char_ref_name}]" if char_ref_name else ""
        print(f"  S{scene_id:02d}{ref_label} 生成中... ", end="", flush=True)
        try:
            ok = gen_func(client, prompt, char_ref, out_file)
            if ok:
                print(f"✓ {out_file.name}", end="", flush=True)
                saved.append(out_file)
                qa = qa_image_with_gemini(client, out_file, prompt, scene_id)
                qa_results.append(qa)
                if qa["ok"]:
                    print("  [QA: OK]")
                else:
                    print(f"  [QA: ⚠️  {len(qa['issues'])}件]")
            else:
                print("⚠️  画像データなし")
        except Exception as e:
            print(f"⚠️  エラー: {e}")

        if scene != scenes[-1]:
            time.sleep(1)

    print(f"\n{'━'*60}")
    print(f"  完了: {len(saved)}/{len(scenes)} 枚 → {out_dir}")
    print(f"{'━'*60}\n")

    # ── 画像QAレポート出力 ──────────────────────────────────
    warnings = [r for r in qa_results if not r["ok"]]
    all_ok = len(warnings) == 0

    print(f"{'━'*60}")
    print(f"  画像QA結果: {len(qa_results) - len(warnings)}/{len(qa_results)} 件 OK")
    if warnings:
        for w in warnings:
            for issue in w["issues"]:
                print(f"  ⚠️  S{w['scene_id']:02d}: {issue}")
    else:
        print(f"  問題なし")
    print(f"{'━'*60}\n")

    episode_dir = DRIVE_BASE / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    qa_file = episode_dir / ("image_qa_result_shorts.json" if shorts else "image_qa_result.json")
    qa_output = {
        "episode_id": episode_id,
        "total_scenes": len(qa_results),
        "warnings": warnings,
        "all_ok": all_ok,
    }
    with open(qa_file, "w", encoding="utf-8") as f:
        json.dump(qa_output, f, ensure_ascii=False, indent=2)
    print(f"  QA結果を保存しました: {qa_file}\n")

    return saved


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles 静止画生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    parser.add_argument("--scenes", default=None,
                        help="特定シーンのみ（例: 1,3,9）。省略時は全シーン")
    parser.add_argument("--shorts", action="store_true",
                        help="Shorts用縦長(9:16)画像をimages_shorts/に生成")
    args = parser.parse_args()

    scene_filter = None
    if args.scenes:
        scene_filter = [int(x.strip()) for x in args.scenes.split(",")]

    run(args.episode, scene_filter=scene_filter, shorts=args.shorts)


if __name__ == "__main__":
    cli()
