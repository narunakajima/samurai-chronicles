"""学習版チャンネルの画像（アイコン）を作る。

アイコン: SC のロゴと同じ赤い円盤に、Tokio の顔とヘッドホン（＝聴く）。小さく表示されても分かるよう、文字は入れない。
          YouTube は正方形の画像を円形に切り抜いて表示するので、円の中に収まるように描く。

使い方:  python3 build_channel_art.py icon
出力:    learning/channel/icon.png（800x800。リポジトリに入れる）と、Drive の samurai-chronicles/learning_channel/ へのコピー
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

BASE_DIR = Path(__file__).parent
SC_DIR = BASE_DIR.parent
OUT_DIR = BASE_DIR / "channel"
DRIVE_OUT = (Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles"
             / "learning_channel")

SIZE = 800
SS = 2                       # 描くときの拡大率（縁をなめらかにするため）
RED_CENTER = (176, 28, 38)   # SC のロゴの赤に合わせる
RED_EDGE = (92, 12, 20)
CREAM = (245, 236, 220)      # ロゴの白い輪
GOLD = (232, 190, 92)
GOLD_DARK = (122, 84, 24)
WHITE_ = (255, 255, 255, 255)
GOLD_RGBA = (240, 200, 110, 255)
CREAM_RGBA = (245, 236, 220, 255)
RING_R = 372                 # 輪の内側の半径（円形に切り抜かれても欠けない大きさ）
RING_W = 14
HEAD_CY = 398              # 頭の中心の高さ（800px 中）


def run(cmd: list):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit(1)


def tokio_still() -> Image.Image:
    """Tokio の立ち絵（背景透過）。本編の素材の動画から1コマ取り出す。"""
    still = BASE_DIR / "build" / "tokio_still.png"
    still.parent.mkdir(parents=True, exist_ok=True)
    if not still.exists():
        run(["ffmpeg", "-y", "-v", "error", "-c:v", "libvpx-vp9", "-ss", "1",
             "-i", SC_DIR / "narrator" / "clips" / "tokio_neutral.webm", "-frames:v", "1", "-pix_fmt", "rgba", still])
    return Image.open(still).convert("RGBA")


def make_icon() -> Image.Image:
    S = SIZE * SS
    c = S // 2
    # 背景: 中心が明るい赤、周りが暗い赤
    mask = Image.radial_gradient("L").resize((S, S), Image.BICUBIC)
    img = Image.composite(Image.new("RGB", (S, S), RED_EDGE), Image.new("RGB", (S, S), RED_CENTER), mask).convert("RGBA")

    # Tokio: 頭の中心を (400, HEAD_CY) に置く（頭の幅 184px を約 350px に拡大。肩から下は円で切れる）
    tk = tokio_still()
    scale = 1.9 * SS
    head_c = (356, 150)   # 立ち絵の中の、頭の中心（頭の上端 y=34、あご y≒265、耳の高さ y≒175、頭の幅 264〜448）
    tk = tk.resize((round(tk.width * scale), round(tk.height * scale)), Image.LANCZOS)
    ox, oy = round(c - head_c[0] * scale), round(HEAD_CY * SS - head_c[1] * scale)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.alpha_composite(tk, (ox, oy)) if ox >= 0 and oy >= 0 else layer.paste(tk, (ox, oy), tk)
    sh = layer.getchannel("A").filter(ImageFilter.GaussianBlur(14 * SS)).point(lambda v: int(v * 0.55))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 255))
    shadow.putalpha(sh)
    img.alpha_composite(shadow, (6 * SS, 8 * SS))
    img.alpha_composite(layer)

    # ヘッドホン: 頭の側面（ear）にカップ、頭の上にバンド
    d = ImageDraw.Draw(img)
    hx = lambda x: round((c + (x - 356) * scale))      # 立ち絵の x → アイコンの x
    hy = lambda y: round(HEAD_CY * SS + (y - 150) * scale)  # 立ち絵の y → アイコンの y
    ear_y = hy(176)
    left_x, right_x = hx(262), hx(450)                  # 耳のあたり（頭の左右の端）
    cup_w, cup_h = 78 * SS, 150 * SS
    # バンド（頭の上を通る太い弧）
    rx = (right_x - left_x) // 2 + 6 * SS
    top = hy(34) - 18 * SS   # 頭の上端のすぐ上を通す（浮かないように）
    ry = ear_y - top
    bw = 24 * SS
    for off, col in ((bw // 2, GOLD_DARK), (0, GOLD)):
        d.arc((c - rx - off, top - off, c + rx + off, top + 2 * ry + off), 180, 360, fill=col,
              width=bw - (0 if off == 0 else 8 * SS))
    # カップ（金の外側＋暗いクッション）
    for cx_ in (left_x, right_x):
        box = (cx_ - cup_w // 2, ear_y - cup_h // 2, cx_ + cup_w // 2, ear_y + cup_h // 2)
        d.rounded_rectangle(box, radius=34 * SS, fill=GOLD_DARK)
        d.rounded_rectangle((box[0] + 4 * SS, box[1] + 4 * SS, box[2] - 4 * SS, box[3] - 4 * SS), radius=30 * SS, fill=GOLD)
        pad_in = 14 * SS
        d.rounded_rectangle((box[0] + pad_in, box[1] + pad_in, box[2] - pad_in, box[3] - pad_in), radius=20 * SS,
                            fill=(38, 30, 30, 255))

    # 円盤の外を切り、ロゴと同じ白い輪を描く
    disc = Image.new("L", (S, S), 0)
    ImageDraw.Draw(disc).ellipse((c - RING_R * SS, c - RING_R * SS, c + RING_R * SS, c + RING_R * SS), fill=255)
    out = Image.new("RGBA", (S, S), RED_EDGE + (255,))
    out.paste(img, (0, 0), ImageChops.multiply(disc, img.getchannel("A") if False else disc))
    ImageDraw.Draw(out).ellipse((c - (RING_R + RING_W) * SS, c - (RING_R + RING_W) * SS,
                                 c + (RING_R + RING_W) * SS, c + (RING_R + RING_W) * SS),
                                outline=CREAM, width=RING_W * SS)
    return out.resize((SIZE, SIZE), Image.LANCZOS).convert("RGB")


def circle_preview(img: Image.Image) -> Image.Image:
    """YouTube での見え方（円形に切り抜き）を、暗い背景に載せて確認する。"""
    prev = Image.new("RGB", (SIZE * 2, SIZE + 40), (24, 24, 24))
    prev.paste(img, (20, 20))
    m = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(m).ellipse((0, 0, SIZE, SIZE), fill=255)
    prev.paste(img, (SIZE + 20, 20), m)
    small = img.resize((98, 98), Image.LANCZOS)
    ms = Image.new("L", (98, 98), 0)
    ImageDraw.Draw(ms).ellipse((0, 0, 98, 98), fill=255)
    prev.paste(small, (SIZE + 20 + SIZE // 2 - 49, 20), ms)  # 実寸（98px）での見え方も、円の上に重ねて確認する
    return prev


# ---- SC のロゴに日本語の文字をかぶせる案（2026-10-23 ユーザー案）
MINCHO = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"   # index 2 = W6（太め。ロゴの SAMURAI CHRONICLES の書体に近い）
LOGO = SC_DIR / "LOGO_dark.PNG"


def _font(size: int):
    from PIL import ImageFont
    return ImageFont.truetype(MINCHO, size, index=2)


def _centered(d, cx, cy, text, font, fill, stroke=0, stroke_fill=(0, 0, 0)):
    b = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
    d.text((cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2), text, font=font, fill=fill,
           stroke_width=stroke, stroke_fill=stroke_fill)


def _centered_logo() -> Image.Image:
    """ロゴを、円盤の中心が画像の中心に来るようにずらして返す。
    元のロゴは円の中心が (405, 380) で、画像の中心 (384, 384) より右にずれている（YouTube は画像の中心で円形に切るので、輪が左右非対称になる）。"""
    src = Image.open(LOGO).convert("RGB")
    out = Image.new("RGB", src.size, src.getpixel((4, 4)))   # はみ出した部分は、ロゴの四隅の暗い色で埋める
    out.paste(src, (-21, 3))
    return out


def _arc_band(d, c, r_in, r_out, a_deg, k):
    """円の上の縁に沿った帯（暗い色＋内側と外側の金の線）。c は円の中心、a_deg は真上から左右に広がる角度（度）。"""
    import math
    n = 160
    ang = [math.radians(-a_deg + 2 * a_deg * i / n) for i in range(n + 1)]
    pt = lambda r, t: (c[0] + r * math.sin(t), c[1] - r * math.cos(t))
    poly = [pt(r_out, t) for t in ang] + [pt(r_in, t) for t in reversed(ang)]
    d.polygon(poly, fill=(24, 12, 14, 255))
    for r, col, w in ((r_out - 3 * k, GOLD, 5 * k), (r_in + 3 * k, GOLD, 5 * k), (r_out - 11 * k, GOLD_DARK, 2 * k), (r_in + 11 * k, GOLD_DARK, 2 * k)):
        d.line([pt(r, t) for t in ang], fill=col, width=round(w), joint="curve")
    for t in (ang[0], ang[-1]):  # 両端の金の線
        d.line([pt(r_in, t), pt(r_out, t)], fill=GOLD, width=round(5 * k))


def _arc_text(img, c, r_text, text, font, fill, spacing):
    """文字を円弧に沿って並べる（真上が中央。1文字ずつ回転して貼る）。"""
    import math
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    cur = -(total / r_text) / 2
    box = round(font.size * 1.8)
    for ch, w in zip(text, widths):
        th = cur + (w / 2) / r_text
        cur += (w + spacing) / r_text
        g = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((box / 2, box / 2), ch, font=font, fill=fill, anchor="mm")
        g = g.rotate(-math.degrees(th), resample=Image.BICUBIC)
        img.alpha_composite(g, (round(c[0] + r_text * math.sin(th) - box / 2), round(c[1] - r_text * math.cos(th) - box / 2)))


def logo_with_text(text: str) -> Image.Image:
    """SC のロゴ（赤い円盤＋兜）の、英字（SAMURAI CHRONICLES、y=486〜642）を帯で覆い、日本語を大きく入れる。
    text の書き方: "上の行|下の行" で2行（上は金色で小さく、下はクリーム色で大きく）。"…@文字" を付けると、兜の上の縁に沿って文字を円弧に並べる。
    帯は暗い色＋金の線（兜の金に合わせる）。円形に切り抜かれても文字が欠けないよう、文字は中央の幅に収める。"""
    text, _, arc = text.partition("@")
    S = SIZE * SS
    k = S / 768  # ロゴの元の大きさ（768px）に対する倍率
    img = _centered_logo().convert("RGBA").resize((S, S), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    two = "|" in text
    by0, by1 = (round(458 * k), round(672 * k)) if two else (round(470 * k), round(660 * k))
    d.rectangle((0, by0, S, by1), fill=(24, 12, 14, 255))
    for y in (by0, by1):
        d.rectangle((0, y - 5 * SS, S, y + 5 * SS), fill=GOLD)
    d.rectangle((0, by0 + 9 * SS, S, by0 + 12 * SS), fill=GOLD_DARK)
    d.rectangle((0, by1 - 12 * SS, S, by1 - 9 * SS), fill=GOLD_DARK)
    cx = round(384 * k)
    if two:
        top, bottom = text.split("|")
        sb = round(min(112, 540 / max(len(bottom), 1)) * k)
        st = round(min(66, 540 / max(len(top), 1)) * k)
        mid = (by0 + by1) // 2
        _centered(d, cx, mid - round(48 * k), top, _font(st), GOLD)
        _centered(d, cx, mid + round(42 * k), bottom, _font(sb), CREAM)
    else:
        size = round(min(130, 540 / max(len(text), 1)) * k)
        size = min(size, round(0.70 * (by1 - by0)))
        _centered(d, cx, (by0 + by1) // 2 + 2 * SS, text, _font(size), CREAM)
    if arc:
        c = (round(384.5 * k), round(383.5 * k))
        r_in, r_out = round(292 * k), round(366 * k)   # 兜の角の先端（中心から約 270px）より外側、円盤の縁（約 373px）より内側
        is_ja = any(ord(ch) > 0x2E80 for ch in arc)
        fs = round((54 if is_ja else 46) * k)
        font = _font(fs)
        spacing = round((8 if is_ja else 5) * k)
        r_text = (r_in + r_out) / 2
        span = (sum(font.getlength(ch) for ch in arc) + spacing * (len(arc) - 1)) / r_text   # 文字列の角度（ラジアン）
        import math
        _arc_band(d, c, r_in, r_out, math.degrees(span) / 2 + 13, k)
        _arc_text(img, c, r_text, arc, font, CREAM, spacing)
    return img.resize((SIZE, SIZE), Image.LANCZOS).convert("RGB")

# ---- バナー（2560x1440）
BW, BH = 2560, 1440
SAFE = (507, 508, 2053, 931)   # すべての機器（スマホ含む）で必ず見える範囲 1546x423
FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"
FONT_TAG = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
FONT_LATIN = "/System/Library/Fonts/Avenir Next.ttc"
YELLOW = (255, 212, 0, 255)
BANNER_COPY_1 = "日本史を聴くだけで"
BANNER_COPY_2 = "英語耳に。"
BANNER_BADGE = "日本史 × 英語リスニング"
BANNER_NAME = "英語で聴く日本史｜Samurai Chronicles"


def _stroke_text(size, items):
    """太い縁取り＋影つきの文字レイヤー。items = [(x, y, 文字, フォント, 色, 縁の太さ)]（x, y は左上）。"""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    for x, y, t, f, col, st in items:
        ds.text((x + 6, y + 8), t, font=f, fill=(0, 0, 0, 190), stroke_width=st, stroke_fill=(0, 0, 0, 190))
        d.text((x, y), t, font=f, fill=col, stroke_width=st, stroke_fill=(0, 0, 0, 255))
    return Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)), layer)


def make_banner() -> Image.Image:
    import random
    from PIL import ImageFont
    # 背景: 左が明るい赤、右へ暗くなる。四隅を暗くし、細かいノイズで質感を出す
    grad = Image.linear_gradient("L").rotate(90, expand=True).resize((BW, BH))   # 左が白→右が黒
    bg = Image.composite(Image.new("RGB", (BW, BH), (168, 26, 36)), Image.new("RGB", (BW, BH), (58, 8, 14)), grad).convert("RGBA")
    vig = Image.radial_gradient("L").resize((BW, BH), Image.BICUBIC).point(lambda v: int(v * 0.55))
    dark = Image.new("RGBA", (BW, BH), (10, 4, 6, 255))
    dark.putalpha(vig)
    bg = Image.alpha_composite(bg, dark)
    rnd = random.Random(7)
    noise = Image.effect_noise((BW, BH), 18).convert("L").point(lambda v: 128 + (v - 128) // 3)
    bg = Image.blend(bg.convert("RGB"), Image.merge("RGB", (noise, noise, noise)), 0.05).convert("RGBA")

    # Tokio の後ろに、赤い光（人物を浮かせる）
    glow = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((1850 - 420, 700 - 360, 1850 + 420, 700 + 360), fill=(230, 70, 60, 120))
    bg = Image.alpha_composite(bg, glow.filter(ImageFilter.GaussianBlur(120)))

    # Tokio（頭の中心を (1850, 705) に置く。肩から下は画面の下端で切れる）
    tk = tokio_still()
    sc = 1.15
    head_c = (356, 150)
    tk = tk.resize((round(tk.width * sc), round(tk.height * sc)), Image.LANCZOS)
    ox, oy = round(1850 - head_c[0] * sc), round(660 - head_c[1] * sc)
    layer = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    layer.paste(tk, (ox, oy), tk)
    sh = layer.getchannel("A").filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.6))
    shadow = Image.new("RGBA", (BW, BH), (0, 0, 0, 255))
    shadow.putalpha(sh)
    bg.alpha_composite(shadow, (10, 12))
    bg.alpha_composite(layer)

    # 名札（Tokio の胸のあたり。本編と同じ書体と色）
    ft1, ft2 = ImageFont.truetype(FONT_TAG, 62), ImageFont.truetype(FONT_TAG, 40)
    items = []
    for t, f, y, col in (("TOKIO KAMIYA", ft1, 822, WHITE_), ("TIME-TRAVEL REPORTER", ft2, 884, GOLD_RGBA)):
        w = f.getbbox(t)[2] - f.getbbox(t)[0]
        items.append((1850 - w // 2, y - 8, t, f, col, 3))

    # 左側に SC のロゴ（パソコン・テレビでだけ見える。スマホの範囲の外）
    logo = _centered_logo().convert("RGBA")
    lm = Image.new("L", logo.size, 0)
    ImageDraw.Draw(lm).ellipse((384 - 352, 384 - 352, 384 + 352, 384 + 352), fill=255)
    logo.putalpha(lm)
    logo = logo.crop((32, 32, 736, 736)).resize((420, 420), Image.LANCZOS)
    lsh = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    lsh.paste(Image.new("RGBA", logo.size, (0, 0, 0, 170)), (254 + 8, 720 - 210 + 10), logo.getchannel("A"))
    bg = Image.alpha_composite(bg, lsh.filter(ImageFilter.GaussianBlur(14)))
    bg.alpha_composite(logo, (254, 720 - 210))

    # コピー（セーフエリアの左側）
    x0 = SAFE[0] + 33
    fb = ImageFont.truetype(FONT_BOLD, 44)
    bw = fb.getbbox(BANNER_BADGE)[2] + 56
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((x0, 532, x0 + bw, 532 + 76), radius=20, fill=GOLD_RGBA)
    d.text((x0 + 28, 543), BANNER_BADGE, font=fb, fill=(25, 20, 10, 255))
    f1 = ImageFont.truetype(FONT_HEAVY, 86)
    f2 = ImageFont.truetype(FONT_HEAVY, 178)
    text = _stroke_text((BW, BH), [(x0 - 6, 628, BANNER_COPY_1, f1, WHITE_, 8), (x0 - 10, 716, BANNER_COPY_2, f2, YELLOW, 11)])
    bg = Image.alpha_composite(bg, text)
    bg = Image.alpha_composite(bg, _stroke_text((BW, BH), items))
    return bg.convert("RGB")


def banner_preview(img: Image.Image) -> Image.Image:
    """機器ごとの見え方（スマホ=中央 1546x423、パソコン=横長の帯 2560x423、テレビ=全体）を並べて確認する。"""
    sx0, sy0, sx1, sy1 = SAFE
    tv = img.resize((1280, 720))
    pc = img.crop((0, sy0, BW, sy1)).resize((1280, round((sy1 - sy0) * 0.5)))
    mobile = img.crop(SAFE)
    out = Image.new("RGB", (1280, 720 + 20 + pc.height + 20 + mobile.height + 20), (24, 24, 24))
    out.paste(tv, (0, 0))
    out.paste(pc, (0, 740))
    out.paste(mobile.resize((mobile.width * 2 // 3, mobile.height * 2 // 3)), (0, 760 + pc.height))
    return out


# ---- SC のバナーに、日本語のチャンネル名を重ねる（2026-10-23 ユーザー案）
SC_BANNER = OUT_DIR / "sc_banner_original.jpg"   # 公開中の Samurai Chronicles のバナー（YouTube API で取得した 2560x1440）


def make_banner_sc(title: str = "英語で聴く|日本史") -> Image.Image:
    """SC のバナーに、日本語のチャンネル名を重ねる。
    "左|右" と書くと、侍の左右に分けて置く（既定。帯の中央の高さに収まり、パソコンの狭い表示でも上端が切れない）。
    "|" がなければ、侍の兜の真上に1行で置く（パソコンで上端が切れることがあったため、既定ではない。2026-10-23）。"""
    from PIL import ImageFont
    img = Image.open(SC_BANNER).convert("RGBA")
    split = "|" in title
    left, right = title.split("|") if split else (title, "")
    font = ImageFont.truetype(MINCHO, 106 if split else 104, index=2)
    cy = 724 if split else 566                  # 分けるときは、帯（y=508〜931）の中央の高さ
    d0 = ImageDraw.Draw(img)

    def box_of(t):
        b = d0.textbbox((0, 0), t, font=font)
        return b, b[2] - b[0], b[3] - b[1]

    # 配置: (文字, 左端 x) の一覧。分けるときは、左の語を侍（中心 x≒1290）の左に右寄せ、右の語を侍の右に左寄せ
    items = []
    if split:
        _, wl, _ = box_of(left)
        items = [(left, 1120 - wl), (right, 1465)]
    else:
        _, wt, _ = box_of(left)
        items = [(left, BW // 2 - wt // 2)]
    # 文字の後ろを少し暗くする（山や霧の明るい所でも読めるように。侍にはかからない）
    dark = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dark)
    for t, x in items:
        b, w, h = box_of(t)
        dd.rounded_rectangle((x - 50, cy - h // 2 - 36, x + w + 50, cy + h // 2 + 56), radius=60, fill=(8, 4, 6, 140))
    img = Image.alpha_composite(img, dark.filter(ImageFilter.GaussianBlur(40)))
    for t, x in items:
        b, w, h = box_of(t)
        tx, ty = x - b[0], cy - h // 2 - b[1]
        shadow = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).text((tx + 4, ty + 7), t, font=font, fill=(0, 0, 0, 230), stroke_width=7, stroke_fill=(0, 0, 0, 230))
        img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(6)))
        d = ImageDraw.Draw(img)
        d.text((tx, ty), t, font=font, fill=CREAM_RGBA, stroke_width=3, stroke_fill=(30, 14, 10, 255))
        # 文字の下の金の線
        yl = cy + h // 2 + 26
        d.rectangle((x, yl - 3, x + w, yl + 3), fill=GOLD_RGBA)
        d.rectangle((x, yl + 9, x + w, yl + 11), fill=(122, 84, 24, 255))
    return img.convert("RGB")

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "banner-sc":
        OUT_DIR.mkdir(exist_ok=True)
        ban = make_banner_sc(*(sys.argv[2:3]))
        ban.save(OUT_DIR / "banner.jpg", quality=93)
        banner_preview(ban).save(BASE_DIR / "build" / "banner_preview.png")
        DRIVE_OUT.mkdir(parents=True, exist_ok=True)
        (DRIVE_OUT / "banner.jpg").write_bytes((OUT_DIR / "banner.jpg").read_bytes())
        print(f"✅ バナー: {OUT_DIR / 'banner.jpg'}（{(OUT_DIR / 'banner.jpg').stat().st_size // 1024} KB。YouTube の上限は 6MB）")
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "banner":
        OUT_DIR.mkdir(exist_ok=True)
        ban = make_banner()
        ban.save(OUT_DIR / "banner.png")
        banner_preview(ban).save(BASE_DIR / "build" / "banner_preview.png")
        DRIVE_OUT.mkdir(parents=True, exist_ok=True)
        (DRIVE_OUT / "banner.png").write_bytes((OUT_DIR / "banner.png").read_bytes())
        print(f"✅ バナー: {OUT_DIR / 'banner.png'}（{(OUT_DIR / 'banner.png').stat().st_size // 1024} KB。YouTube の上限は 6MB）")
        sys.exit(0)
    if len(sys.argv) >= 2 and sys.argv[1] == "icon-logo":
        texts = sys.argv[2:] or ["英語耳", "聴く日本史", "日本史×英語"]
        sheet = Image.new("RGB", (SIZE * len(texts) + 20 * (len(texts) + 1), SIZE + 40 + 120), (24, 24, 24))
        for i, t in enumerate(texts):
            v = logo_with_text(t)
            v.save(BASE_DIR / "build" / f"icon_logo_{i}.png")
            m = Image.new("L", (SIZE, SIZE), 0)
            ImageDraw.Draw(m).ellipse((0, 0, SIZE, SIZE), fill=255)
            sheet.paste(v, (20 + i * (SIZE + 20), 20), m)
            sm = v.resize((98, 98), Image.LANCZOS)
            ms = Image.new("L", (98, 98), 0)
            ImageDraw.Draw(ms).ellipse((0, 0, 98, 98), fill=255)
            sheet.paste(sm, (20 + i * (SIZE + 20) + SIZE // 2 - 49, SIZE + 40), ms)  # 実寸（98px）
        sheet.save(BASE_DIR / "build" / "icon_logo_sheet.png")
        print("✅ build/icon_logo_sheet.png")
        sys.exit(0)
    if len(sys.argv) != 2 or sys.argv[1] != "icon":
        print(__doc__)
        sys.exit(1)
    OUT_DIR.mkdir(exist_ok=True)
    icon = make_icon()
    icon.save(OUT_DIR / "icon.png")
    circle_preview(icon).save(BASE_DIR / "build" / "icon_preview.png")
    DRIVE_OUT.mkdir(parents=True, exist_ok=True)
    (DRIVE_OUT / "icon.png").write_bytes((OUT_DIR / "icon.png").read_bytes())
    print(f"✅ アイコン: {OUT_DIR / 'icon.png'}（Drive: {DRIVE_OUT / 'icon.png'}）")
