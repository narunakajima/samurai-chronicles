"""
sc_image_gen.py — Samurai Chronicles 静止画生成スクリプト

使い方:
  python3 sc_image_gen.py --episode ep001
  python3 sc_image_gen.py --episode ep001 --scenes 1,3,9   # 特定シーンのみ再生成

出力先: ~/Desktop/SC/{episode_id}/images/（確認用。/sc-new STEP4でユーザーOK後に
  Google Driveのsamurai-chronicles/{episode_id}/images/へ移動する）
  S01.png, S02.png, ... S20.png

キャラクター参照:
  ep001.json の各シーンに "character_ref": "musashi" がある場合、
  characters/musashi.txt のキャラクター設定が BASE_CONTEXT に追加される。

Shorts(9:16)生成について（2026-08-02〜）:
  --shorts は本編(16:9, images/S{id}.png)が既に生成済みならそれをGeminiで
  9:16に再構成する（ゼロから独立生成しない）。必ず本編を先に生成すること。
  本編画像が無い場合はテキストのみから独立生成する（フォールバック）。
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

MODEL = "gemini-3.1-flash-image"
QA_MODEL = "gemini-flash-latest"

BASE_DIR = Path(__file__).parent  # スクリプト・エピソードJSONの場所

# 生成素材の保存先（確認用。/sc-new STEP4でOK後にGoogle Driveへ移動する）
DESKTOP_BASE = Path.home() / "Desktop" / "SC"

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
    "Period-accurate Edo/Sengoku era attire: kimono, samurai armor, period weapons only. "
    "Unless a character reference specifies otherwise (e.g. a monk's shaved head, "
    "a woman's hair, a ninja's covered hair, a ronin's unbound hair), default male "
    "hairstyles to a period-accurate chonmage (topknot with shaved pate) — never a "
    "modern haircut. "
    "When a scene depicts a sealed letter or document, use a period-accurate Japanese "
    "seal — a red vermillion ink stamp (shuin) or a paper cord tie (mizuhiki) — never "
    "a Western-style wax seal with ribbon. "
    "When a scene requires lighting from a lamp or lantern, use a traditional Japanese "
    "light source — a paper andon lantern, a chochin paper lantern, or a simple wax "
    "candle (rousoku) on a plain stand — never a Western-style glass oil lamp, "
    "hurricane lamp, or metal lamp with a wick-adjustment knob."
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


def _generate_with_retry(client, contents, output_path: Path, max_retries: int = 3) -> bool:
    """generate_content を最大 max_retries 回リトライする（指数バックオフ）。
    contents は文字列プロンプト、または [プロンプト, PIL.Image] のような
    マルチモーダル入力（画像編集・再構成用）のどちらも受け付ける。"""
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                ),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    output_path.write_bytes(part.inline_data.data)
                    return True
            return False
        except Exception as e:
            if attempt < max_retries:
                wait = 5 * (2 ** attempt)  # 5s, 10s, 20s
                time.sleep(wait)
            else:
                raise


def generate_one_image_portrait(client, scene_prompt: str, character_ref: str, output_path: Path,
                                 ref_image: Image.Image = None) -> bool:
    """Shorts用縦長(9:16)画像を生成する。

    ref_image が指定された場合（本編16:9で既にQA承認済みの画像がある場合）は、
    ゼロから再生成せずその画像を9:16に再構成する（同一構図・同一キャラクター外見を
    維持しつつ縦画角に拡張する）。QAで一度承認済みの内容を流用するため、
    MISMATCH等の再発が起きにくく、コスト面でも失敗時の再試行を減らせる。
    ref_image が無い場合（本編画像が未生成、または --shorts 単独実行等）は
    従来通りテキストのみから新規生成する。
    """
    if ref_image is not None:
        prompt = (
            "Reframe this exact reference image into a 9:16 vertical portrait composition for "
            "mobile short-form video. Keep the same subject, character appearance, setting, "
            "lighting, and art style exactly as in the reference image — do not change the "
            "scene content. Extend/recompose the framing so the main subject is centered and "
            "prominent in a vertical frame, generating plausible additional scene content "
            "above/below as needed to fill the vertical canvas.\n\n"
            f"Scene: {scene_prompt}"
        )
        return _generate_with_retry(client, [prompt, ref_image], output_path)

    parts = [
        "Cinematic vertical short film still, 9:16 format. "
        "Subject centered and prominent in frame. Composed for portrait mobile viewing. "
        + BASE_CONTEXT,
    ]
    if character_ref:
        parts.append(f"Character reference: {character_ref}")
    parts.append(f"Scene: {scene_prompt}")
    full_prompt = "\n\n".join(parts)
    return _generate_with_retry(client, full_prompt, output_path)


def generate_one_image(client, scene_prompt: str, character_ref: str, output_path: Path,
                        ref_image: Image.Image = None) -> bool:
    """1シーン1枚生成して output_path に保存。成功すれば True を返す。
    ref_image は本編(16:9)生成では使わない（gen_func の呼び出しシグネチャ統一のため受け取るのみ）。"""
    parts = [BASE_CONTEXT]
    if character_ref:
        parts.append(f"Character reference: {character_ref}")
    parts.append(f"Scene: {scene_prompt}")
    full_prompt = "\n\n".join(parts)
    return _generate_with_retry(client, full_prompt, output_path)


def _correction_note(issues: list) -> str:
    """QAで見つかった issue の種類ごとに、プロンプトへ追記する修正指示を組み立てる。"""
    notes = []
    seen = set()
    for issue in issues:
        prefix = issue.split(":", 1)[0].strip().upper()
        if prefix == "TEXT" and prefix not in seen:
            notes.append(
                "Absolutely no readable text, letters, calligraphy, signage, "
                "banners with writing, or watermarks anywhere in the image."
            )
        elif prefix == "ARCHITECTURE" and prefix not in seen:
            notes.append(
                "Ensure all armor, clothing, and architecture are strictly "
                "authentic to the correct historical period as described — "
                "no anachronistic later-era styles. Any lamp or lantern "
                "must be a traditional Japanese andon, chochin, or wax candle (rousoku) — "
                "never a Western-style oil lamp or glass-shaded lamp. Any sealed letter or "
                "document must use a red vermillion ink stamp (shuin) or paper cord tie "
                "(mizuhiki) — never a Western-style wax seal with ribbon."
            )
        elif prefix == "HAIRSTYLE" and prefix not in seen:
            notes.append(
                "Fix the hairstyle: unless the character is explicitly a monk, woman, ninja, "
                "masterless ronin written as deliberately unkempt, young child, or non-Japanese "
                "character, render a proper sakayaki — the front and top of the scalp shaved "
                "completely bare and smooth — with the remaining hair oiled flat and folded "
                "forward into a small, compact, tightly-bound chonmage topknot resting flat "
                "against the crown. Do NOT render a full unshaved head of hair merely tied back "
                "into a ponytail or bun (no shaved forehead is still wrong even if it looks "
                "old-fashioned), and do NOT render a modern buzz cut, undercut, or styled haircut. "
                "The topknot must read as a deliberate groomed knot, not a loose sprouting tuft."
            )
        elif prefix == "DISTORTION" and prefix not in seen:
            notes.append(
                "Render all hands, faces, and anatomy with correct, natural "
                "proportions — no malformed or distorted body parts."
            )
        elif prefix == "MISMATCH" and prefix not in seen:
            notes.append(
                "Follow the scene description exactly — do not add extra "
                "elements or deviate from the specified composition, subject, "
                "and setting."
            )
        elif prefix == "STYLE" and prefix not in seen:
            notes.append(
                "Render in a strictly photorealistic cinematic concept-art / film-still style — "
                "natural photographic skin texture, volumetric directional lighting, realistic "
                "proportions and materials. Do not render as a flat illustration, cel-shaded art, "
                "anime/manga style, or hand-painted graphic-novel panel."
            )
        seen.add(prefix)
    return " ".join(notes)


def build_retry_prompt(base_prompt: str, issues: list, level: int) -> str:
    """
    QA失敗時の再生成用プロンプトを組み立てる。
    - 問題の種類に応じた定型の修正指示（_correction_note）に加えて、
      QAが検出した issue の原文をそのまま「Specific issues」として渡す。
      定型指示だけでは MISMATCH（構図の食い違い）等の具体的な差分が
      伝わらず的外れな再生成になりがちなため、QAの生テキストを直接
      フィードバックすることで再試行の的中率を上げる。
    - level 3以上（max_attempts を増やした場合用に残置）: 大きく構図を変える指示を追記。
    """
    note = _correction_note(issues)
    prompt = base_prompt
    if note:
        prompt = f"{prompt}\n\nIMPORTANT CORRECTIONS: {note}"
    if issues:
        specific = "\n".join(f"- {issue}" for issue in issues)
        prompt = (
            f"{prompt}\n\nSpecific issues detected by QA in the previous attempt "
            f"(fix these exactly):\n{specific}"
        )
    if level >= 3:
        prompt = (
            f"{prompt}\n\nUse a substantially different camera angle, framing, "
            "and composition from a typical rendering of this scene, to avoid "
            "repeating the same generation issues."
        )
    return prompt


def _generate_and_qa(client, gen_func, base_prompt: str, char_ref: str,
                      out_file: Path, scene_id: int, max_attempts: int = 2,
                      ref_image: Image.Image = None) -> dict:
    """
    生成 → QA を行い、クリティカル（QA失敗）なら自動的にプロンプトを修正して
    最大 max_attempts 回まで再試行する。
    attempt 1: 元のプロンプトのまま
    attempt 2以降: QA issue の原文＋種類別の修正指示を追記
    それでも解決しない場合は最終結果をそのまま返す（呼び出し元でユーザー確認）。

    2026-08-02改訂: 実績データ（89エピソード分のQA結果）で、3回目まで
    リトライしても最終的にNGのまま終わるケースが本編38.5%・Shorts39.1%と
    高頻度だったため、デフォルトを3→2回に削減してコストを抑える
    （3回目の追加コストに見合う改善効果が確認できなかったため）。
    """
    qa_result = {"scene_id": scene_id, "ok": False, "issues": ["画像生成失敗（QA未実行）"], "attempts": 0}
    prompt = base_prompt
    for attempt in range(1, max_attempts + 1):
        suffix = f"（{attempt}回目）" if attempt > 1 else ""
        print(f"生成中{suffix}... ", end="", flush=True)
        try:
            ok = gen_func(client, prompt, char_ref, out_file, ref_image)
        except Exception as e:
            print(f"⚠️  エラー: {e}")
            qa_result["attempts"] = attempt
            return qa_result
        if not ok:
            print("⚠️  画像データなし")
            qa_result["attempts"] = attempt
            return qa_result
        print(f"✓ {out_file.name}", end="", flush=True)
        qa_result = qa_image_with_gemini(client, out_file, base_prompt, scene_id)
        qa_result["attempts"] = attempt
        if qa_result["ok"]:
            print("  [QA: OK]")
            return qa_result
        print(f"  [QA: ⚠️  {len(qa_result['issues'])}件]")
        if attempt < max_attempts:
            next_level = attempt + 1
            print(f"     → {'構図を変更して' if next_level == 3 else '修正指示付きで'}自動再生成します")
            prompt = build_retry_prompt(base_prompt, qa_result["issues"], next_level)
        else:
            print(f"     → {max_attempts}回試行して未解決。ユーザー確認へ")
    return qa_result


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
            "- STYLE: the rendering does not match a photorealistic cinematic concept-art / film-still "
            "look (natural skin texture, volumetric photographic lighting, realistic proportions). Flag "
            "images that instead look flat, cel-shaded, hand-painted-illustration, anime/manga, or like a "
            "graphic-novel panel — this series must look consistently photorealistic across every scene.\n"
            "- ARCHITECTURE: anachronistic or era-incorrect architecture, objects, or clothing for "
            "Edo/Sengoku Japan. This includes light sources — flag Western-style "
            "oil lamps, glass-shaded lamps, candlesticks, or electric-style lighting fixtures; "
            "period-correct light sources are andon (paper-and-wood lanterns), chochin (paper "
            "lanterns), or open torches/fire only. This also includes document seals — flag a "
            "Western-style wax seal with ribbon on any letter or scroll; period-correct sealing "
            "is a red vermillion ink stamp (shuin) or a paper cord tie (mizuhiki).\n"
            "- HAIRSTYLE: any male adult samurai/warrior character whose hair is not period-correct "
            "for Edo/Sengoku Japan. The historically correct default is a sakayaki (the front and top "
            "of the scalp shaved bare) with the remaining hair oiled and tied into a compact chonmage "
            "topknot folded flat against the crown. Flag ALL of the following as issues, not only "
            "obviously modern cuts:\n"
            "  (a) a clearly modern haircut (undercut, short back and sides, styled/gelled hair, "
            "contemporary fade, buzz cut/crew cut covering the whole scalp with no shave line)\n"
            "  (b) a full, unshaved head of hair merely swept back or tied into a ponytail/bun with "
            "NO shaved forehead/pate visible — this is just as incorrect as a modern cut and must "
            "be flagged even though it may look 'old-fashioned'\n"
            "  (c) the topknot itself rendered wrong — sprouting straight up as a loose tuft, "
            "frizzy/unbound, or otherwise not reading as a deliberate folded, tied knot\n"
            "The only valid exceptions are: a monk's fully shaved head, a woman's hair, a ninja's "
            "covered/hidden hair, an explicitly masterless ronin or low-status character whose "
            "scene description calls for deliberately unkempt/unbound hair as a character choice, "
            "young children (forelock/maegami styles), or non-Japanese/Western characters. If the "
            "scene description does not explicitly call for one of these exceptions, the sakayaki+chonmage "
            "look is required.\n\n"
            f"Scene description: {image_prompt}\n\n"
            "Respond with ONLY a JSON object, no other text, in this exact format:\n"
            '{"ok": true, "issues": []}\n'
            "or\n"
            '{"ok": false, "issues": ["ISSUE_TYPE: brief description", ...]}'
        )

        response = client.models.generate_content(
            model=QA_MODEL,
            contents=[qa_prompt, image],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            ),
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
    except Exception as e:
        # QA自体が失敗した場合はサイレントにOK扱いせず、issueとして扱い
        # 既存のリトライ機構に乗せる（API障害等を「問題なし」と誤認しないため）。
        return {"scene_id": scene_id, "ok": False, "issues": [f"QA_ERROR: {e}"]}


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
        # "teaser"（S19次回予告）はsc_video_gen.pyのShorts選定（gen_video内）が
        # 今エピソードと無関係な人物・場面のため除外しているのと合わせて対象外にする
        # （2026-09-04〜。以前はteaserも候補に入れていたため、動画側で使われない
        # Shorts画像を毎話1枚無駄に生成していた）。
        priority_types = ["hook", "climax", "insight", "falling_action", "outro", "rising_action", "setup"]
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

        # --scenes 指定がある場合は selected_ids をさらに絞り込む
        if scene_filter:
            selected_ids = {sid for sid in selected_ids if sid in scene_filter}

        # scene_id 順にソート
        scenes = sorted([s for s in all_scenes if s["scene_id"] in selected_ids], key=lambda s: s["scene_id"])
        out_dir = DESKTOP_BASE / episode_id / "images_shorts"
        gen_func = generate_one_image_portrait
        label = "Shorts縦長(9:16)"
        # 再生成対象のファイルのみ削除（指定外シーンの既存PNGは保持）
        if out_dir.exists():
            for s in scenes:
                fp = out_dir / f"S{s['scene_id']:02d}.png"
                if fp.exists():
                    fp.unlink()
    else:
        scenes = ep["scenes"]
        if scene_filter:
            scenes = [s for s in scenes if s["scene_id"] in scene_filter]
        out_dir = DESKTOP_BASE / episode_id / "images"
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

        # Shorts生成時: 本編(16:9)で既にQA承認済みの画像があれば、それを9:16に
        # 再構成する（ゼロから独立生成しない）。無ければ従来通りテキストのみで生成。
        ref_image = None
        if shorts:
            main_img_path = DESKTOP_BASE / episode_id / "images" / f"S{scene_id:02d}.png"
            if main_img_path.exists():
                try:
                    ref_image = Image.open(main_img_path)
                except Exception:
                    ref_image = None

        ref_label = f" [{char_ref_name}]" if char_ref_name else ""
        reuse_label = " (本編流用)" if ref_image is not None else ""
        print(f"  S{scene_id:02d}{ref_label}{reuse_label} ", end="", flush=True)
        qa = _generate_and_qa(client, gen_func, prompt, char_ref, out_file, scene_id, ref_image=ref_image)
        qa_results.append(qa)
        if out_file.exists():
            saved.append(out_file)

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
    avg_attempts = sum(r.get("attempts", 1) for r in qa_results) / len(qa_results) if qa_results else 0
    print(f"  平均試行回数: {avg_attempts:.2f}回/シーン（コスト効果測定用）")
    print(f"{'━'*60}\n")

    episode_dir = DESKTOP_BASE / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    qa_file = episode_dir / ("image_qa_result_shorts.json" if shorts else "image_qa_result.json")
    qa_output = {
        "episode_id": episode_id,
        "total_scenes": len(qa_results),
        "warnings": warnings,
        "all_ok": all_ok,
        # 全シーンの試行回数（成功・失敗問わず）。リトライ回数の妥当性を後で検証するためのログ。
        "scene_attempts": [
            {"scene_id": r["scene_id"], "attempts": r.get("attempts", 1), "ok": r["ok"]}
            for r in qa_results
        ],
    }
    with open(qa_file, "w", encoding="utf-8") as f:
        json.dump(qa_output, f, ensure_ascii=False, indent=2)
    print(f"  QA結果を保存しました: {qa_file}\n")

    return saved


def run_face(episode_id: str):
    """Shorts冒頭用の顔アップ画像を生成 → images_shorts/S00_face.png"""
    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    face_prompt = ep.get("shorts_face_image_prompt", "")
    if not face_prompt:
        print(f"❌ 'shorts_face_image_prompt' フィールドがありません: {ep_json}")
        sys.exit(1)

    # character_ref は scenes[0] または主要シーンから取得（任意）
    scenes = ep.get("scenes", [])
    char_ref_name = next(
        (s.get("character_ref") for s in scenes if s.get("character_ref")), None
    )
    char_ref = load_character_ref(char_ref_name) if char_ref_name else ""

    out_dir = DESKTOP_BASE / episode_id / "images_shorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "S00_face.png"

    client = genai.Client(api_key=API_KEY)

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — Shorts顔アップ画像生成")
    print(f"  出力先: {out_file}")
    print(f"{'━'*60}\n")

    print(f"  S00_face ", end="", flush=True)
    qa_result = _generate_and_qa(
        client, generate_one_image_portrait, face_prompt, char_ref, out_file, 0
    )

    # QA結果をJSONに保存（STEP 5D で読み込まれる）
    episode_dir = DESKTOP_BASE / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    qa_file = episode_dir / "image_qa_result_face.json"
    qa_output = {
        "episode_id": episode_id,
        "total_scenes": 1,
        "warnings": [] if qa_result["ok"] else [qa_result],
        "all_ok": qa_result["ok"],
    }
    with open(qa_file, "w", encoding="utf-8") as f:
        json.dump(qa_output, f, ensure_ascii=False, indent=2)
    print(f"  QA結果を保存しました: {qa_file}")

    print(f"\n{'━'*60}\n")


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles 静止画生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    parser.add_argument("--scenes", default=None,
                        help="特定シーンのみ（例: 1,3,9）。省略時は全シーン")
    parser.add_argument("--shorts", action="store_true",
                        help="Shorts用縦長(9:16)画像をimages_shorts/に生成")
    parser.add_argument("--face", action="store_true",
                        help="Shorts冒頭顔アップ画像を生成（images_shorts/S00_face.png）")
    args = parser.parse_args()

    if args.face:
        run_face(args.episode)
        return

    scene_filter = None
    if args.scenes:
        scene_filter = [int(x.strip()) for x in args.scenes.split(",")]

    run(args.episode, scene_filter=scene_filter, shorts=args.shorts)


if __name__ == "__main__":
    cli()
