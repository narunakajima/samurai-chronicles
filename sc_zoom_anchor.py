#!/usr/bin/env python3
"""
sc_zoom_anchor.py — シーン画像の主被写体重心をGemini Visionで判定し、
episode JSONにzoom_anchorを書き込む。

使い方:
  python3 sc_zoom_anchor.py --episode ep001
  python3 sc_zoom_anchor.py --episode ep001 --scenes 3,7   # 特定シーンのみ再判定

2026-08-04〜: 以前はClaude自身がReadツールで対象シーン画像を全て読み込んで
判定していたが（最大20枚/話）、メイン会話のコンテキストとClaude利用枠を
圧迫するため、sc_image_gen.pyの画像QAと同じ考え方でGemini Visionへ委任する
方式に変更した。

対象シーン: character_ref が設定されているシーン。
2人構図かどうかは image_prompt のキーワードだけでは判定しない
（"facing" "opposite" "two-shot" のような表現は "on the left"/"on the right"
を伴わないことが多く、旧ロジックでは二人シーンを1人構図として誤判定していた
— 2026-08-26、ep088のKatsu/Saigo対談シーンで発覚）。
代わりにGemini Vision自体に「画面内の主要な人物が1人か2人以上か」を判定させ、
2人以上の場合は zoom_anchor に {"multi_person": true} を書き込む。
sc_video_gen.py 側はこれを見て pan_zoom_out（両者を収める構図）に切り替える。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from PIL import Image
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-flash-latest"

BASE_DIR = Path(__file__).parent
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)


def is_target_scene(scene: dict) -> bool:
    """zoom_anchorを判定すべきシーンか（character_refあり）。
    1人構図か2人構図かはこの時点では判定しない（Gemini Visionに委ねる）。"""
    return bool(scene.get("character_ref"))


def determine_zoom_anchor(client, image_path: Path) -> dict:
    """Gemini Visionで主被写体の構図を判定する。

    画面内の主要な人物が2人以上いる場合は {"multi_person": true} を返す
    （このシーンは1点ズームではなく両者を収めるpan_zoom_outで扱うべきため）。
    主要な人物が1人の場合は、その顔〜胸あたりの重心を正規化座標で返す。
    """
    image = Image.open(image_path)
    prompt = (
        "This is a cinematic concept-art still from a historical documentary.\n"
        "Classify this image's composition as exactly one of:\n\n"
        "- SINGLE: there is one clearly dominant human subject — the one most "
        "central, closest to camera, most sharply lit/in focus, or the one other "
        "people are oriented toward/addressing. This applies even if several other "
        "people are also visible (a crowd, students, guards, soldiers, bystanders), "
        "as long as one figure is clearly the compositional focus and the others are "
        "secondary/supporting.\n"
        "- TWO_SHOT: there are exactly two people who are CO-EQUAL subjects of the "
        "shot — similar size and visual prominence, neither one clearly dominant over "
        "the other, both clearly posed as the joint focus (e.g. two people facing "
        "each other in conversation, seated across a table from each other). Do NOT "
        "classify as TWO_SHOT just because 2+ people are visible — only when there is "
        "no single dominant figure among them.\n\n"
        "If TWO_SHOT, respond with ONLY:\n"
        '{"multi_person": true}\n\n'
        "If SINGLE, identify the dominant subject's face-to-chest area center of mass "
        "and respond with ONLY:\n"
        '{"x": 0.0, "y": 0.0}\n'
        "(x: 0.0=left edge, 1.0=right edge; y: 0.0=top edge, 1.0=bottom edge)\n\n"
        "Respond with ONLY the JSON object, no other text."
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=[prompt, image],
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    result = json.loads(text)
    if result.get("multi_person"):
        return {"multi_person": True}
    return {"x": round(float(result["x"]), 2), "y": round(float(result["y"]), 2)}


def run(episode_id: str, scene_filter: list = None):
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    images_dir = DRIVE_BASE / episode_id / "images"
    client = genai.Client(api_key=API_KEY)

    targets = [s for s in ep["scenes"] if is_target_scene(s)]
    if scene_filter:
        targets = [s for s in targets if s["scene_id"] in scene_filter]

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — zoom_anchor 判定（Gemini Vision）")
    print(f"  対象シーン: {len(targets)}/{len(ep['scenes'])}")
    print(f"{'━'*60}\n")

    updated = 0
    failed = []
    for scene in targets:
        scene_id = scene["scene_id"]
        img_path = images_dir / f"S{scene_id:02d}.png"
        if not img_path.exists():
            print(f"  ⚠️  S{scene_id:02d}: 画像が見つかりません（スキップ）")
            failed.append(scene_id)
            continue
        try:
            anchor = determine_zoom_anchor(client, img_path)
            scene["zoom_anchor"] = anchor
            updated += 1
            if anchor.get("multi_person"):
                print(f"  S{scene_id:02d}: multi_person（two-shot構図と判定）")
            else:
                print(f"  S{scene_id:02d}: x={anchor['x']}, y={anchor['y']}")
        except Exception as e:
            print(f"  ⚠️  S{scene_id:02d}: 判定失敗（{e}）— zoom_anchorはnullのまま")
            failed.append(scene_id)

    with open(ep_json, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)

    print(f"\n{'━'*60}")
    print(f"  完了: {updated}/{len(targets)} シーンに zoom_anchor を書き込みました")
    if failed:
        print(f"  要確認: {', '.join(f'S{s:02d}' for s in failed)}")
    print(f"{'━'*60}\n")


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles zoom_anchor判定（Gemini Vision）")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    parser.add_argument("--scenes", default=None, help="特定シーンのみ（例: 3,7）。省略時は全対象シーン")
    args = parser.parse_args()

    scene_filter = None
    if args.scenes:
        scene_filter = [int(x.strip()) for x in args.scenes.split(",")]

    run(args.episode, scene_filter=scene_filter)


if __name__ == "__main__":
    cli()
