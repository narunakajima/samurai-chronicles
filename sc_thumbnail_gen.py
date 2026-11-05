#!/usr/bin/env python3
"""
sc_thumbnail_gen.py — /sc-new STEP 3B のサムネイル生成（スクリプト化）

以前は STEP 3B が「インラインの Python（python3 -c / python3 -）」で書かれていたため、
無人実行（handoff-poller。Bash は許可されたスクリプトの呼び出しだけ）では動かせなかった
（2026-11-05 修正）。同じ処理を、引数つきのスクリプト呼び出しの形にした。

使い方:
  python3 sc_thumbnail_gen.py --episode ep120 --title "THE GOD OF WAR" --subtitle "Japan's Greatest Betrayal"
  python3 sc_thumbnail_gen.py --episode ep120 --title "..." --subtitle "..." --force   # 既存を作り直す

- エピソード JSON の `thumbnail_prompt` に、STEP 3B 規定のテキストオーバーレイ指示を足して Gemini で生成する
- 出力: ~/Desktop/SC/ep{NNN}_thumbnail.png（1280x720 に整える）。既存ファイルは --force なしでは上書きしない（課金の二重払い防止）
- タイトル重複チェック: 他エピソードの thumbnail_prompt に同じ大文字タイトルがあれば止まる
  （--allow-duplicate-title で無視。2026-09 の「サムネイルタイトル重複チェック」ルール）
- Tokio モードの回は、この後 `python3 sc_tokio_assets.py thumb --image ~/Desktop/SC/ep{NNN}_thumbnail.png` を実行する（別コマンド）
- APIキーは GEMINI_API_KEY_SC を優先（SC の請求に計上するため）。失敗時は sys.exit(1)
"""
import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
EPISODES_DIR = BASE_DIR / "episodes"
DESKTOP_SC = Path.home() / "Desktop" / "SC"
RETRIES = 3
SIZE = (1280, 720)

OVERLAY = (
    'Bold text overlay at the top in large white block letters with dark drop shadow: "{title}". '
    'Smaller text at the bottom in white: "{subtitle}". '
    "Text must be clearly legible, sharp, and properly spelled. "
    "Photorealistic live-action cinematic film still, 35mm anamorphic lens, real skin texture, "
    "natural film grain, realistic lighting. NOT illustration, NOT anime, NOT cartoon, "
    "NOT concept art, NOT comic style. 16:9 aspect ratio, 1280x720."
)


def die(msg: str):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def normalize_episode(s: str) -> str:
    m = re.search(r"(\d+)", s)
    if not m:
        die(f"エピソード番号を読み取れません: {s}")
    return f"ep{int(m.group(1)):03d}"


def check_duplicate_title(ep: str, title: str) -> list[str]:
    hits = []
    needle = title.strip().lower()
    for p in sorted(EPISODES_DIR.glob("ep*.json")):
        if p.stem == ep:
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        blob = " ".join(str(d.get(k, "")) for k in ("thumbnail_prompt", "thumbnail_title", "thumbnail_text")).lower()
        if f'"{needle}"' in blob or f"'{needle}'" in blob:
            hits.append(p.stem)
    return hits


def fit_to_size(data: bytes) -> bytes:
    """1280x720 に中央クロップ＋リサイズして PNG にする（PIL がなければそのまま返す）。"""
    try:
        from PIL import Image
    except Exception:
        return data
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    target = SIZE[0] / SIZE[1]
    if abs(w / h - target) > 0.01:
        if w / h > target:
            nw = int(h * target)
            im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / target)
            im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize(SIZE, Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description="SC サムネイル生成（/sc-new STEP 3B）")
    ap.add_argument("--episode", required=True)
    ap.add_argument("--title", required=True, help="大文字の肩書き・形容（例: THE GOD OF WAR）。人物名そのままは避ける")
    ap.add_argument("--subtitle", required=True, help="サブコピー（例: Japan's Greatest Betrayal）")
    ap.add_argument("--force", action="store_true", help="既存のサムネイルを作り直す")
    ap.add_argument("--allow-duplicate-title", action="store_true")
    args = ap.parse_args()

    ep = normalize_episode(args.episode)
    ep_json = EPISODES_DIR / f"{ep}.json"
    if not ep_json.exists():
        die(f"{ep_json} がありません")
    data = json.load(open(ep_json, encoding="utf-8"))
    base_prompt = (data.get("thumbnail_prompt") or "").strip()
    if not base_prompt:
        die(f"{ep}.json に thumbnail_prompt がありません")

    title = args.title.strip().upper()
    subtitle = args.subtitle.strip()
    dups = check_duplicate_title(ep, title)
    if dups and not args.allow_duplicate_title:
        die(f'タイトル "{title}" は既存の thumbnail_prompt と重複しています: {", ".join(dups)}（別のタイトルにするか --allow-duplicate-title）')

    out = DESKTOP_SC / f"{ep}_thumbnail.png"
    if out.exists() and not args.force:
        die(f"{out} が既にあります（作り直すなら --force）")

    api_key = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        die("GEMINI_API_KEY_SC / GEMINI_API_KEY が設定されていません")

    from google import genai
    from google.genai import types
    try:
        from sc_image_gen import MODEL  # 画像生成モデルは sc_image_gen.py と統一
    except Exception:
        MODEL = "gemini-nano-banana-2.1"

    full_prompt = base_prompt + "\n\n" + OVERLAY.format(title=title, subtitle=subtitle)
    client = genai.Client(api_key=api_key)
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=full_prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            img = None
            for cand in (resp.candidates or []):
                for part in (cand.content.parts or []):
                    if getattr(part, "inline_data", None) is not None and part.inline_data.data:
                        img = part.inline_data.data
                        break
                if img:
                    break
            if not img:
                raise RuntimeError("画像が返りませんでした")
            DESKTOP_SC.mkdir(parents=True, exist_ok=True)
            out.write_bytes(fit_to_size(img))
            print(f"✓ サムネイルを保存しました: {out}（{MODEL}、{attempt}回目）")
            print(f"  タイトル: {title} / サブ: {subtitle}")
            print("  ※ 文字の綴り・顔・髪型を目視で確認すること（Read ツールで画像を開く）")
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"⚠️  {attempt}/{RETRIES} 回目に失敗: {e}", file=sys.stderr)
            time.sleep(3 * attempt)
    die(f"サムネイルの生成に失敗しました: {last_err}")


if __name__ == "__main__":
    main()
