"""
sc_tokio_assets.py — 語り手 Tokio の素材づくり（話すループの生成・背景抜き・サムネイル合成）

2026-10-17、ep116（Tokio パイロット）の作業をコマンドにまとめたもの。Tokio の設定・声・注意点は
narrator/tokio.json、動画への重ね方は sc_video_gen.py（add_tokio_overlay）を参照。

サブコマンド:
  gen-talk  : 基準画像から Veo 3.1 fast で「話している間のループ」（6秒）を作る（課金: 1本 約$0.9）
              → narrator/raw/tokio_{expr}_talk.mp4
  key       : raw の動画から使う区間を切り出し、マゼンタ背景を抜いて透過 webm にする
              → narrator/clips/tokio_{expr}_talk.webm（往復ループ _pp.webm は動画生成時に自動で作り直される）
  thumb     : サムネイルの右下に Tokio（neutral の立ち絵）と名札を合成する
              → 元画像は {名前}_no_tokio.png に退避して上書き。合成済みかどうかはハッシュで判定するので、
                何度実行しても二重に重ならず、サムネイルを作り直したあとは新しい原画から合成する
  check     : narrator/clips の各 webm の中身を、灰色の背景に重ねたコンタクトシートにする（目視確認用）

使い方:
  python3 sc_tokio_assets.py gen-talk --expr thinking surprised     # 課金。既存は --force で作り直し
  python3 sc_tokio_assets.py key --expr thinking                    # 既定の区間（WINDOWS）で背景抜き
  python3 sc_tokio_assets.py key --expr writing --start 1.8 --len 3.2
  python3 sc_tokio_assets.py check --out /tmp/tokio_sheet.png       # 作った中身を必ず目で確認する
  python3 sc_tokio_assets.py thumb --image ~/Desktop/SC/ep117_thumbnail.png

⚠️ ffmpeg は subprocess にリストで渡し、失敗したら標準エラーを表示して終了する（2026-10-17 の教訓:
   シェルで変数にオプションを入れて呼ぶと zsh では1つの引数になって失敗し、しかもバックグラウンド実行
   では失敗が見えず、古い素材のまま動画を作ってしまった）。
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_DIR = Path(__file__).parent
NARR_DIR = BASE_DIR / "narrator"
RAW_DIR = NARR_DIR / "raw"
CLIP_DIR = NARR_DIR / "clips"
BASE_IMAGE = RAW_DIR / "tokio_neutral_base_half_v2.png"
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
DIN_FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"

VEO_MODEL = "veo-3.1-fast-generate-preview"
OP_TIMEOUT_SEC = 600   # Veo の完了待ちの上限（秒）
EXPRESSIONS = ["neutral", "thinking", "moved", "writing", "surprised"]   # wry は廃止（笑いが出て安定しない）

# 使う区間（秒）。Veo の6秒のうち、ポーズと表情が保たれている部分。3秒以降は頭が傾いて崩れやすい
WINDOWS = {
    "neutral": (0.0, 3.2),
    "thinking": (0.0, 3.6),
    "moved": (1.5, 3.2),     # 冒頭は手帳がまだ閉じている（開くのは1.5秒まで）
    "writing": (1.8, 3.2),     # 冒頭は手帳がまだ閉じている
    "surprised": (0.4, 3.2),
}

# Veo のプロンプト。2026-10-17 の教訓（narrator/tokio.json の talk_notes 参照）:
#  - 「表情とポーズを正確に保つ」を強く書くと表情の違いが消える → 表情ごとに具体的な動きを書く
#  - ただし眉を持ち上げ続ける指示は不自然（surprised）。『普通の高さで、強調に合わせて少し・短く』
#  - 笑い・記号・文字は禁止。音声は安全フィルタにかかるので "No sound" ではなく環境音を書き、音声は -an で捨てる
HEAD = ("The man is TALKING in a composed way like a field reporter giving a report, throughout the whole clip: "
        "his mouth opens and closes naturally in clear speech movements, with small natural nods and gentle breathing. ")
TAIL = (" Do NOT laugh and do NOT smile. Do NOT draw any symbols, text, speech bubbles, sparkles or effect lines. "
        "Camera locked, no zoom, no pan. The flat pure magenta (#FF00FF) background stays perfectly uniform and unchanged. "
        "Keep the exact painterly concept-art look, same face and clothing. Ambient audio: soft distant wind only.")
HOLD = " Both hands keep holding the closed leather notebook at chest height."
MID = {
    "neutral": ("His eyes stay on the viewer with a serious, composed look, one natural blink." + HOLD),
    "thinking": ("CLEARLY thoughtful and searching: his eyes are open and look up and to the side, away from the viewer, "
                 "as if recalling something, his brow is furrowed and his lips purse between words, his head tilts slightly "
                 "and his chin lifts a little. He does not look at the viewer." + HOLD),
    "moved": ("CLEARLY moved and tender, speaking softly. He holds the leather notebook OPEN in his left hand at chest height, "
              "its pages turned toward him (within the first second he opens the cover; the notebook is open for the rest of the clip), "
              "and his glossy, slightly wet eyes look down and read the open pages as he speaks; near the end he lifts his eyes "
              "gently toward the distance. The inner ends of his eyebrows are raised in a gentle sorrowful look and his lips tremble "
              "a little between words. His right hand rests lightly on the edge of the notebook; he does not write."),
    "writing": ("He is writing: his head is bowed and his eyes look down at the open leather notebook in his left hand; "
                "his right hand holds a pencil and writes in the notebook with small clear pencil strokes the whole time "
                "while he keeps speaking quietly; he glances up toward the viewer once near the end."),
    "surprised": ("A mild, natural, attentive reaction: his eyebrows stay at a normal level most of the time and rise only "
                  "slightly and briefly, once or twice, in rhythm with his speech, like an ordinary person emphasising a word. "
                  "His eyes stay normal, only a little more open at the emphasis. No wide-eyed stare at any time." + HOLD),
}


def run(cmd: list, what: str):
    """subprocess を実行し、失敗したら標準エラーを表示して終了する（失敗を見逃さない）。"""
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"❌ {what} が失敗しました:\n{r.stderr[-1500:]}")
        sys.exit(1)


def raw_path(expr: str) -> Path:
    return RAW_DIR / f"tokio_{expr}_talk.mp4"


def clip_path(expr: str) -> Path:
    return CLIP_DIR / f"tokio_{expr}_talk.webm"


# ── gen-talk ──────────────────────────────────────────────────────────

def cmd_gen_talk(args):
    from google import genai
    from google.genai import types
    key = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)
    if not BASE_IMAGE.exists():
        print(f"❌ 基準画像がありません: {BASE_IMAGE}")
        sys.exit(1)
    if args.force and not args.expr:
        # --force だけだと全5表情（約$4.5）を作り直してしまう。作り直す表情を明示させる
        print("❌ --force は、作り直す表情を --expr で指定してください（例: --expr thinking）。全表情の再生成は約$4.5かかります")
        sys.exit(1)
    exprs = args.expr or EXPRESSIONS
    todo = [e for e in exprs if args.force or not raw_path(e).exists()]
    for e in exprs:
        if e not in todo:
            print(f"  スキップ（生成済み）: {raw_path(e).name}（作り直すなら --force --expr {e}）")
    print(f"  生成予定: {len(todo)}本（{', '.join(todo) or 'なし'}） — 費用の目安 約${len(todo) * 0.9:.1f}")
    if args.dry_run or not todo:
        return
    client = genai.Client(api_key=key)
    img = types.Image(image_bytes=BASE_IMAGE.read_bytes(), mime_type="image/png")

    def one(expr):
        # 生成（ここで課金）と、ダウンロード・保存を分ける。動画が返った後に失敗しても、生成し直さない（二重課金を避ける）
        video = None
        reason = ""
        for _ in range(2):   # 動画が返らないとき（安全フィルタ・APIエラー）だけ1回取り直す。返らなかった分は課金されない
            try:
                op = client.models.generate_videos(
                    model=VEO_MODEL, prompt=HEAD + MID[expr] + TAIL, image=img,
                    config=types.GenerateVideosConfig(aspect_ratio="9:16", duration_seconds=6, number_of_videos=1))
                waited = 0
                while not op.done and waited < OP_TIMEOUT_SEC:
                    time.sleep(10)
                    waited += 10
                    op = client.operations.get(op)
                if not op.done:
                    reason = f"{OP_TIMEOUT_SEC}秒待っても完了しません（途中で打ち切り）"
                    continue
                if getattr(op, "error", None):
                    reason = f"API エラー: {op.error}"
                    continue
                resp = op.response
                if resp and resp.generated_videos:
                    video = resp.generated_videos[0]
                    break
                reason = (f"動画が返りませんでした（安全フィルタの可能性。"
                          f"rai_media_filtered_reasons={getattr(resp, 'rai_media_filtered_reasons', None)}）")
            except Exception as e:  # noqa: BLE001
                reason = f"生成の呼び出しで例外: {str(e)[:200]}"
        if video is None:
            return expr, f"FAILED（{reason}）"
        for attempt in range(3):   # 生成済みの動画のダウンロードだけを再試行する
            try:
                client.files.download(file=video.video)
                video.video.save(str(raw_path(expr)))
                return expr, "ok"
            except Exception as e:  # noqa: BLE001
                reason = f"ダウンロード・保存で例外: {str(e)[:200]}"
                time.sleep(5)
        return expr, f"FAILED（生成は成功・課金済み。{reason}）"

    with ThreadPoolExecutor(max(1, len(todo))) as ex:
        for expr, res in ex.map(one, todo):
            print(f"  {expr}: {res}")
    print("次に: key で背景を抜き、check で中身を目で確認する（表情が出ているか・手帳を持っているか・笑っていないか）")


# ── key ───────────────────────────────────────────────────────────────

def cmd_key(args):
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    for expr in args.expr:
        src = raw_path(expr)
        if not src.exists():
            print(f"❌ 素の動画がありません: {src}（先に gen-talk）")
            sys.exit(1)
        start, length = WINDOWS[expr]
        if args.start is not None:
            start = args.start
        if args.len is not None:
            length = args.len
        run([FFMPEG, "-y", "-v", "error", "-ss", start, "-t", length, "-i", src, "-an",
             "-vf", "crop=720:960:0:160,colorkey=0xFF00FF:0.34:0.06,format=yuva444p,erosion,erosion,format=yuva420p",
             "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24", "-auto-alt-ref", "0",
             clip_path(expr)], f"{expr} の背景抜き")
        print(f"  ✓ {clip_path(expr).name}（{start}〜{start + length:.1f}秒）")
    print("次に: check で中身を目で確認する。往復ループ（_pp.webm）は動画生成時に自動で作り直される")


# ── check ─────────────────────────────────────────────────────────────

def cmd_check(args):
    from PIL import Image
    exprs = args.expr or EXPRESSIONS
    tmp = Path("/tmp/sc_tokio_check")
    tmp.mkdir(exist_ok=True)
    rows = []
    for expr in exprs:
        p = clip_path(expr)
        if not p.exists():
            print(f"  （なし）{p.name}")
            continue
        frames = []
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(p)], capture_output=True, text=True)
        dur = float(r.stdout.strip() or 3.0)
        for i, t in enumerate(round(dur * f, 2) for f in (0.05, 0.35, 0.65, 0.95)):   # クリップの長さに合わせて抜く
            out = tmp / f"{expr}_{i}.png"
            run([FFMPEG, "-y", "-v", "error", "-c:v", "libvpx-vp9", "-ss", t, "-i", p, "-frames:v", "1",
                 "-vf", "crop=500:640:110:0,scale=190:-2", "-pix_fmt", "rgba", out], f"{expr} のコマ抽出")
            frames.append(out)
        rows.append(frames)
    if not rows:
        print("❌ 確認する動画がありません")
        sys.exit(1)
    h = Image.open(rows[0][0]).height
    sheet = Image.new("RGB", (190 * 4, h * len(rows)), (60, 70, 80))
    for r, frames in enumerate(rows):
        for c, f in enumerate(frames):
            im = Image.open(f).convert("RGBA")
            bg = Image.new("RGBA", im.size, (60, 70, 80, 255))
            bg.alpha_composite(im)
            sheet.paste(bg.convert("RGB"), (190 * c, h * r))
    out = Path(args.out).expanduser()
    sheet.save(out)
    print(f"  ✓ コンタクトシート: {out}（行=表情、列=クリップの5%/35%/65%/95%の位置）")


# ── thumb ─────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_thumb(args):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    img_path = Path(args.image).expanduser()
    if not img_path.exists():
        print(f"❌ サムネイルがありません: {img_path}")
        sys.exit(1)
    backup = img_path.with_name(img_path.stem + "_no_tokio.png")
    marker = img_path.with_name(img_path.stem + ".tokio_done")   # 合成後の画像のハッシュ。二重合成の判定に使う
    already = marker.exists() and marker.read_text().strip() == _sha256(img_path)
    if already:
        # いま img_path は合成済み → 退避した原画から合成し直す（二重に重ねない）
        if not backup.exists():
            print(f"❌ 合成済みですが、退避した原画がありません: {backup}")
            sys.exit(1)
        src_img = backup
    else:
        # 合成前の画像（初回、またはサムネイルを作り直した後）→ 原画として退避し、そこから合成する
        shutil.copy(img_path, backup)
        src_img = backup
    still = Path("/tmp/sc_tokio_still.png")
    run([FFMPEG, "-y", "-v", "error", "-c:v", "libvpx-vp9", "-ss", 1, "-i", CLIP_DIR / "tokio_neutral.webm",
         "-frames:v", "1", "-pix_fmt", "rgba", still], "Tokio の立ち絵の抽出")
    th = Image.open(src_img).convert("RGBA")
    tk = Image.open(still).convert("RGBA")
    bb = tk.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox()
    tk = tk.crop(bb)
    W, H = th.size
    h = int(H * args.scale)                 # 主役より小さく（既定は高さ約40%。サブコピーと重なる回は --scale で小さくする）
    w = int(tk.width * h / tk.height)
    tk = tk.resize((w, h), Image.LANCZOS)
    shadow_a = tk.getchannel("A").filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.65))
    blk = Image.new("RGBA", tk.size, (0, 0, 0, 255))
    blk.putalpha(shadow_a)
    x, y = W - w - 14, H - h
    sh = Image.new("RGBA", th.size, (0, 0, 0, 0))
    sh.alpha_composite(blk, (x + 4, y + 3))
    out = Image.alpha_composite(th, sh)
    out.alpha_composite(tk, (x, y))
    # 名札（頭の上）
    f1 = ImageFont.truetype(DIN_FONT, 44)
    f2 = ImageFont.truetype(DIN_FONT, 28)
    cx = x + w // 2
    lines = (("TOKIO KAMIYA", f1, y - 49, (255, 255, 255, 255)), ("TIME-TRAVEL REPORTER", f2, y + 1, (240, 200, 110, 255)))
    layer = Image.new("RGBA", th.size, (0, 0, 0, 0))
    sh2 = Image.new("RGBA", th.size, (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(sh2)
    for text, font, ty, col in lines:
        tw = font.getbbox(text)[2] - font.getbbox(text)[0]
        tx = min(cx - tw // 2, W - tw - 12)   # 小さく合成したとき名札が右端で切れないように
        d.text((tx, ty), text, font=font, fill=col)
        ds.text((tx + 2, ty + 3), text, font=font, fill=(0, 0, 0, 255))
    out = Image.alpha_composite(out, sh2.filter(ImageFilter.GaussianBlur(3)))
    out = Image.alpha_composite(out, layer)
    out.convert("RGB").save(img_path)
    marker.write_text(_sha256(img_path))
    print(f"  ✓ Tokio を合成しました: {img_path}（原画: {backup.name}。もう一度実行しても二重には重ならない）")


def main():
    ap = argparse.ArgumentParser(description="語り手 Tokio の素材づくり")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("gen-talk", help="話すループを Veo で生成（課金）")
    p.add_argument("--expr", nargs="+", choices=EXPRESSIONS, default=None, help="省略時は全表情（--force のときは必須）")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_gen_talk)
    p = sub.add_parser("key", help="使う区間を切り出して背景を抜く")
    p.add_argument("--expr", nargs="+", choices=EXPRESSIONS, default=EXPRESSIONS)
    p.add_argument("--start", type=float)
    p.add_argument("--len", type=float)
    p.set_defaults(fn=cmd_key)
    p = sub.add_parser("check", help="背景抜き後の中身をコンタクトシートにする")
    p.add_argument("--expr", nargs="+", choices=EXPRESSIONS)
    p.add_argument("--out", default="/tmp/tokio_sheet.png")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("thumb", help="サムネイルに Tokio と名札を合成")
    p.add_argument("--image", required=True)
    p.add_argument("--scale", type=float, default=0.40, help="Tokio の高さ（サムネイル高さに対する比。既定 0.40）")
    p.set_defaults(fn=cmd_thumb)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
