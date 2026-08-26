#!/usr/bin/env python3
"""
sc_scene_review.py — 動画生成前のシーン確認ページ生成

STEP 5A（TTS）/ 5B（画像）完了後、STEP 6（動画生成）に進む前に、
「ナレーション（英語音声）と画像が対応しているか」を人間が実際に聴きながら
確認するためのローカルHTMLページを生成する。各シーンごとに画像・ナレーション
再生プレーヤー・日本語訳（制作確認書から抽出）を並べて表示する。

Gemini等による自動判定ではなく、動画生成前の人間によるオーディオ・ビジュアル
突き合わせ確認を目的とする（動画生成は素材によっては数十分かかるため、
生成前にこの確認を済ませることで手戻りを防ぐ）。

使い方:
  python3 sc_scene_review.py --episode ep088

出力: ~/Desktop/SC/ep088_review.html
"""
import argparse
import base64
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DESKTOP_SC = Path.home() / "Desktop" / "SC"
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)

SCENE_BLOCK_RE = re.compile(
    r"▶ S(\d+)\s+\[(\w+)\].*?\n+"
    r"\s*【EN】\s*\n(?P<en>.*?)\n+"
    r"\s*【JA】\s*\n(?P<ja>.*?)\n+"
    r"-{5,}",
    re.DOTALL,
)

OVERALL_REVIEW_RE = re.compile(
    r"【総評】\s*\n(?P<body>.*?)\n+={5,}",
    re.DOTALL,
)


def compute_scene_bgm_roles(scenes: list) -> list:
    """各シーンに intro/main/outro のどのBGM役割が対応するかを、
    sc_video_gen.py の compute_bgm_segments と同じロジックで判定する。

    境界1 = 最初の rising_action/climax シーン（序盤→中盤）
    境界2 = 最後の climax シーンの次（中盤→終盤）
    """
    types = [s.get("type", "") for s in scenes]
    n = len(scenes)

    b1_idx = next((i for i, t in enumerate(types) if t in ("rising_action", "climax")), n // 3)
    climax_idxs = [i for i, t in enumerate(types) if t == "climax"]
    b2_idx = (climax_idxs[-1] + 1) if climax_idxs else (n * 2 // 3)
    if b2_idx <= b1_idx or b2_idx >= n:
        b2_idx = min(max(b1_idx + 1, n * 2 // 3), n - 1)

    roles = []
    for i in range(n):
        if i < b1_idx:
            roles.append("intro")
        elif i < b2_idx:
            roles.append("main")
        else:
            roles.append("outro")
    return roles


def find_bgm_files(episode_id: str, ep_data: dict) -> dict:
    """役割ごとのBGM候補ファイルを探す。
    STEP4完了前（Desktop/SC/BGM/に選定3曲が残っている段階）を優先し、
    見つからなければ episode JSON の bgm_sources（STEP4後）→ 命名規則の順にフォールバックする。"""
    result = {}
    bgm_dir = DESKTOP_SC / "BGM"
    bgm_sources = ep_data.get("bgm_sources") or {}
    for role in ("intro", "main", "outro"):
        matches = sorted(bgm_dir.glob(f"{role}_*.mp3")) if bgm_dir.exists() else []
        if matches:
            result[role] = matches[0]
            continue
        src = bgm_sources.get(role)
        if src:
            candidate = DRIVE_BASE / src
            if candidate.exists():
                result[role] = candidate
                continue
        drive_match = sorted((DRIVE_BASE / "BGM").glob(f"{episode_id}-BGM-{role}.mp3")) \
            if (DRIVE_BASE / "BGM").exists() else []
        if drive_match:
            result[role] = drive_match[0]
    return result


def parse_review_doc(review_path: Path) -> dict:
    """制作確認書からシーンごとのEN/JAナレーションを抽出する。"""
    text = review_path.read_text(encoding="utf-8")
    result = {}
    for m in SCENE_BLOCK_RE.finditer(text):
        scene_id = int(m.group(1))
        en = m.group("en").strip()
        ja = m.group("ja").strip()
        result[scene_id] = {"en": en, "ja": ja}
    return result


def parse_overall_review(review_path: Path) -> str:
    """制作確認書の【総評】セクションを抽出する。"""
    text = review_path.read_text(encoding="utf-8")
    m = OVERALL_REVIEW_RE.search(text)
    return m.group("body").strip() if m else ""


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def sniff_image_mime(data: bytes) -> str:
    """sc_image_gen.py の出力は拡張子が .png でも実体がJPEGのことがあるため、
    ファイル先頭バイトから実際の画像形式を判定する（拡張子は信用しない）。"""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/png"  # フォールバック


def data_uri(path: Path, mime: str = None) -> str:
    """ローカルファイルをbase64データURIに変換する。
    file:// 参照はブラウザのローカルファイルアクセス制限（特にSafari）で
    読み込めないことがあるため、画像・音声とも埋め込み方式にする。"""
    data = path.read_bytes()
    if mime is None:
        mime = sniff_image_mime(data)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_html(episode_id: str, scenes: list, narrations: dict, images_dir: Path,
               audio_dir: Path, bgm_files: dict, overall_review: str = "") -> str:
    # BGMは役割ごとに1回だけ埋め込む（シーンごとに重複埋め込みするとファイルサイズが膨れるため）。
    bgm_uris = {role: data_uri(path, "audio/mpeg") for role, path in bgm_files.items()}
    bgm_elements = "\n".join(
        f'<audio id="bgm-{role}" preload="none" src="{uri}"></audio>'
        for role, uri in bgm_uris.items()
    )
    bgm_role_label = {"intro": "序盤", "main": "中盤", "outro": "終盤"}

    scene_roles = compute_scene_bgm_roles(scenes)

    rows = []
    for scene, role in zip(scenes, scene_roles):
        sid = scene["scene_id"]
        stype = scene.get("type", "")
        cref = scene.get("character_ref") or "—"
        img_path = images_dir / f"S{sid:02d}.png"
        audio_path = audio_dir / f"S{sid:02d}.wav"
        narr = narrations.get(sid, {"en": scene.get("narration", ""), "ja": "（制作確認書に訳文が見つかりません）"})

        img_tag = (
            f'<img src="{data_uri(img_path)}" alt="S{sid:02d}">'
            if img_path.exists()
            else '<div class="missing">画像が見つかりません</div>'
        )
        audio_tag = (
            f'<audio controls src="{data_uri(audio_path, "audio/wav")}"></audio>'
            if audio_path.exists()
            else '<div class="missing">音声が見つかりません</div>'
        )
        if role in bgm_uris:
            bgm_controls = (
                f'<div class="bgm-controls">'
                f'<button class="bgm-toggle" data-role="{role}" data-label="{bgm_role_label[role]}" '
                f'onclick="toggleBgm(\'{role}\')">▶ {bgm_role_label[role]}BGM再生</button>'
                f'</div>'
            )
        else:
            bgm_controls = f'<div class="bgm-controls missing">{bgm_role_label[role]}BGMが見つかりません</div>'

        rows.append(f"""
        <section class="scene">
          <h2>S{sid:02d} <span class="type">[{html_escape(stype)}]</span>
              <span class="cref">キャラクター: {html_escape(cref)}</span>
              <span class="bgm-role">BGM役割: {bgm_role_label[role]}</span></h2>
          <div class="scene-body">
            <div class="scene-image">{img_tag}</div>
            <div class="scene-text">
              {audio_tag}
              {bgm_controls}
              <p class="en">{html_escape(narr['en'])}</p>
              <p class="ja">{html_escape(narr['ja'])}</p>
            </div>
          </div>
        </section>
        """)

    if overall_review:
        overall_block = f"""
<section class="overall">
  <h2>総評（制作確認書より）</h2>
  <p class="overall-body">{html_escape(overall_review).replace(chr(10), '<br>')}</p>
</section>
"""
    else:
        overall_block = ""

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>{episode_id} シーン確認</title>
<style>
  body {{ font-family: -apple-system, "Hiragino Sans", sans-serif; background: #1c1c1e; color: #eee;
          max-width: 900px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 20px; }}
  .scene {{ border-bottom: 1px solid #444; padding: 20px 0; }}
  .scene h2 {{ font-size: 16px; margin: 0 0 12px; }}
  .type {{ color: #8ab4f8; font-weight: normal; margin-left: 8px; }}
  .cref {{ color: #999; font-weight: normal; margin-left: 12px; font-size: 13px; }}
  .scene-body {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .scene-image img {{ max-width: 420px; width: 100%; border-radius: 6px; display: block; }}
  .scene-text {{ flex: 1; min-width: 260px; }}
  audio {{ width: 100%; margin-bottom: 12px; }}
  .en {{ color: #aaa; font-size: 13px; line-height: 1.5; }}
  .ja {{ color: #fff; font-size: 15px; line-height: 1.7; margin-top: 8px; }}
  .missing {{ color: #e66; font-size: 13px; padding: 40px 0; text-align: center; border: 1px dashed #644; }}
  .bgm-role {{ color: #f4b942; font-weight: normal; margin-left: 12px; font-size: 13px; }}
  .bgm-controls {{ margin-bottom: 12px; }}
  .bgm-controls button {{ background: #333; color: #eee; border: 1px solid #555; border-radius: 4px;
                           padding: 4px 10px; margin-right: 6px; font-size: 13px; cursor: pointer; }}
  .bgm-controls button:hover {{ background: #444; }}
  .bgm-controls.missing {{ color: #e66; font-size: 12px; }}
  .overall {{ background: #262629; border: 1px solid #444; border-radius: 8px; padding: 16px 20px; margin-bottom: 8px; }}
  .overall h2 {{ font-size: 15px; margin: 0 0 10px; color: #f4b942; }}
  .overall-body {{ font-size: 14px; line-height: 1.8; color: #ddd; margin: 0; }}
</style>
</head>
<body>
<h1>{episode_id} — シーン確認（画像 × ナレーション × BGM × 日本語訳）</h1>
<p style="color:#999;font-size:13px;">動画生成前の突き合わせ確認用。ナレーション音声・そのシーンのBGMを聴きながら、画像内容と日本語訳が対応しているか確認してください。</p>
{overall_block}
{bgm_elements}
{"".join(rows)}
<script>
function toggleBgm(role) {{
  const el = document.getElementById('bgm-' + role);
  if (!el) return;
  if (el.paused) {{
    ['intro', 'main', 'outro'].forEach(function(r) {{
      if (r !== role) {{
        const other = document.getElementById('bgm-' + r);
        if (other) other.pause();
      }}
    }});
    el.play();
  }} else {{
    el.pause();
  }}
}}
function setBgmButtonState(role, playing) {{
  document.querySelectorAll('button[data-role="' + role + '"]').forEach(function(btn) {{
    btn.textContent = playing ? ('⏸ ' + btn.dataset.label + 'BGM停止') : ('▶ ' + btn.dataset.label + 'BGM再生');
  }});
}}
['intro', 'main', 'outro'].forEach(function(role) {{
  const el = document.getElementById('bgm-' + role);
  if (!el) return;
  el.addEventListener('play', function() {{ setBgmButtonState(role, true); }});
  el.addEventListener('pause', function() {{ setBgmButtonState(role, false); }});
}});
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="動画生成前のシーン確認ページ（画像+ナレーション再生+日本語訳）を生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep088）")
    args = parser.parse_args()
    episode_id = args.episode

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}", file=sys.stderr)
        sys.exit(1)
    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    review_path = DESKTOP_SC / f"{episode_id}_制作確認書.txt"
    narrations = {}
    overall_review = ""
    if review_path.exists():
        narrations = parse_review_doc(review_path)
        overall_review = parse_overall_review(review_path)
        if not overall_review:
            print(f"⚠️  制作確認書に【総評】が見つかりませんでした（{review_path}）", file=sys.stderr)
    else:
        print(f"⚠️  制作確認書が見つかりません（{review_path}）。日本語訳なしで生成します。", file=sys.stderr)

    images_dir = DESKTOP_SC / episode_id / "images"
    audio_dir = DRIVE_BASE / episode_id / "audio"

    bgm_files = find_bgm_files(episode_id, ep)
    missing_roles = [r for r in ("intro", "main", "outro") if r not in bgm_files]
    if missing_roles:
        print(f"⚠️  BGMが見つかりません: {', '.join(missing_roles)}", file=sys.stderr)

    html = build_html(episode_id, ep["scenes"], narrations, images_dir, audio_dir, bgm_files, overall_review)

    out_path = DESKTOP_SC / f"{episode_id}_review.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — シーン確認ページを生成しました")
    print(f"  {out_path}")
    print(f"  ブラウザで開いて確認してください（Finderで開く操作は自動実行しません）")
    print(f"{'━'*60}\n")


if __name__ == "__main__":
    main()
