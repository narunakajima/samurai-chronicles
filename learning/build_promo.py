"""学習版の本編に誘導するための、サムネイルとショート動画を作る。

コンセプト（毎回共通・ユーザー決定 2026-10-23）:
  「日本史を聴くだけで、英語が聞き取れるようになる（英語耳に）」を、はっきり伝える。
  サムネイル: 本編の印象的な画像＋Tokio＋大きなキャッチコピー＋英文を少しだけ見せる
  ショート:   「英語で言える？」のクイズ → 本編の英文で答え合わせ → Tokio の一言解説 → 本編への誘導

回ごとに変わる内容は、台本（lessons/ep{NNN}.json）の "promo" 欄に書く:
  "promo": {"thumb_scene": 1, "thumb_en": "Honnoji is burning.",
            "short": {...}}

使い方:
  python3 build_promo.py thumb ep106
  python3 build_promo.py short ep106
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = Path(__file__).parent
SC_DIR = BASE_DIR.parent
DRIVE = Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles"

# ---- 毎回共通のコンセプト（ここを変えると全回のサムネイル・ショートが変わる）
COPY_1 = "日本史を聴くだけで"
COPY_2 = "英語耳に。"
BADGE = "日本史 × 英語リスニング"

FONT_JA_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
FONT_JA_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"
FONT_EN = "/System/Library/Fonts/Avenir Next.ttc"  # index 0 = Bold
FONT_TAG = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"  # Tokio の名札（本編と同じ）
YELLOW = (255, 212, 0, 255)
GOLD = (240, 200, 110, 255)
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)

TW, TH = 1280, 720  # サムネイル


def run(cmd: list, cwd=None):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit(1)


def load(ep_id: str):
    lesson = json.loads((BASE_DIR / "lessons" / f"{ep_id}.json").read_text(encoding="utf-8"))
    if "promo" not in lesson:
        print(f"台本に promo 欄がありません: lessons/{ep_id}.json")
        sys.exit(1)
    return lesson


def cover(img: Image.Image, w: int, h: int, anchor=(0.5, 0.5), place=(0.5, 0.5), zoom=1.0) -> Image.Image:
    """縦横比を保って w×h を覆うように拡大して切り出す。画像の anchor（被写体の位置。0〜1）が、
    出力の place の位置に来るように切り出す（zoom で少し大きくして、ずらす余地を作る）。"""
    s = max(w / img.width, h / img.height) * zoom
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x = min(max(0, round(anchor[0] * img.width - place[0] * w)), img.width - w)
    y = min(max(0, round(anchor[1] * img.height - place[1] * h)), img.height - h)
    return img.crop((x, y, x + w, y + h))


def scene_anchor(ep_id: str, sid: int):
    ep = json.loads((SC_DIR / "episodes" / f"{ep_id}.json").read_text(encoding="utf-8"))
    za = next(x for x in ep["scenes"] if x["scene_id"] == sid).get("zoom_anchor") or {}
    return float(za.get("x", 0.5)), float(za.get("y", 0.5))


def tokio_still(work: Path) -> Image.Image:
    """Tokio の立ち絵（背景透過）を、本編の素材の動画から1コマ取り出す（SC のサムネイルと同じ方法）。"""
    still = work / "tokio_still.png"
    if not still.exists():
        run(["ffmpeg", "-y", "-v", "error", "-c:v", "libvpx-vp9", "-ss", "1",
             "-i", SC_DIR / "narrator" / "clips" / "tokio_neutral.webm", "-frames:v", "1", "-pix_fmt", "rgba", still])
    tk = Image.open(still).convert("RGBA")
    return tk.crop(tk.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox())


def lift_dark(im: Image.Image) -> Image.Image:
    """暗部を持ち上げる（動画の TOKIO_LIFT_CURVE 0/0.06 0.35/0.42 1/1 と同じ折れ線）。"""
    lut = [int(round(255 * (0.06 + v / 255 / 0.35 * 0.36 if v / 255 <= 0.35 else 0.42 + (v / 255 - 0.35) / 0.65 * 0.58))) for v in range(256)]
    r, g, b, a = im.split()
    return Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))


def gold_glow(tk: Image.Image, radius: int, gain: float = 2.0) -> Image.Image:
    """Tokio の形をぼかして金色に塗った光のレイヤー（tk と同じ大きさ。はみ出す分は余白を足してある）。"""
    pad = radius * 3
    a = Image.new("L", (tk.width + 2 * pad, tk.height + pad), 0)
    a.paste(tk.getchannel("A"), (pad, pad))
    a = a.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, int(v * gain)))
    g = Image.new("RGBA", a.size, (240, 200, 110, 255))
    g.putalpha(a)
    return g, pad


def text_layer(size, items):
    """太い縁取り＋影つきの文字を描いたレイヤーを返す。items = [(x, y, 文字, フォント, 色, 縁の太さ)]"""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    for x, y, s, font, col, stroke in items:
        ds.text((x + 4, y + 6), s, font=font, fill=(0, 0, 0, 200), stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
        d.text((x, y), s, font=font, fill=col, stroke_width=stroke, stroke_fill=BLACK)
    out = Image.alpha_composite(Image.new("RGBA", size, (0, 0, 0, 0)), shadow.filter(ImageFilter.GaussianBlur(6)))
    return Image.alpha_composite(out, layer)


def fit_font(path: str, s: str, max_w: int, start: int, index: int = 0) -> ImageFont.FreeTypeFont:
    size = start
    while size > 10:
        f = ImageFont.truetype(path, size, index=index)
        if f.getbbox(s)[2] - f.getbbox(s)[0] <= max_w:
            return f
        size -= 4
    return ImageFont.truetype(path, size, index=index)


def cmd_thumb(ep_id: str):
    lesson = load(ep_id)
    promo = lesson["promo"]
    work = BASE_DIR / "build" / ep_id
    work.mkdir(parents=True, exist_ok=True)
    sid = promo.get("thumb_scene", 1)
    # 主役（被写体）を、左のコピーと右の Tokio の間（横 60% の位置）に来るように置く
    bg = cover(Image.open(DRIVE / ep_id / "images" / f"S{sid:02d}.png").convert("RGBA"), TW, TH,
               anchor=scene_anchor(ep_id, sid), place=(0.60, 0.45), zoom=1.15)

    # 左側を暗くして、文字を読みやすくする（右側の Tokio と主役の画像は残す）
    grad = Image.new("L", (TW, 1))
    for x in range(TW):
        grad.putpixel((x, 0), int(max(0.0, 1 - x / (TW * 0.55)) * 210))
    shade = Image.new("RGBA", (TW, TH), (0, 0, 0, 255))
    shade.putalpha(grad.resize((TW, TH)))
    img = Image.alpha_composite(bg, shade)

    # Tokio（右下、高さ約66%。主役より控えめに）
    tk = tokio_still(work)
    h = int(TH * 0.66)
    tk = tk.resize((int(tk.width * h / tk.height), h), Image.LANCZOS)
    x_t = TW - tk.width - 10
    if json.loads((SC_DIR / "episodes" / f"{ep_id}.json").read_text(encoding="utf-8")).get("tokio_glow"):
        gl, pad = gold_glow(tk, 14)     # 暗い背景でも埋もれないよう、黒い影の代わりに金色の光（ep119〜）
        img.alpha_composite(gl, (x_t - pad, TH - h - pad))
        tk = lift_dark(tk)
    else:
        sh_a = tk.getchannel("A").filter(ImageFilter.GaussianBlur(12)).point(lambda v: int(v * 0.7))
        sh = Image.new("RGBA", tk.size, (0, 0, 0, 255))
        sh.putalpha(sh_a)
        img.alpha_composite(sh, (x_t + 6, TH - h + 4))
    img.alpha_composite(tk, (x_t, TH - h))
    # 名札（頭の上。本編のサムネイル・動画と同じ書体と色）
    ft1, ft2 = ImageFont.truetype(FONT_TAG, 46), ImageFont.truetype(FONT_TAG, 30)
    cx, ty = x_t + tk.width // 2, TH - h - 92
    tag = []
    for s_, f_, y_, col in (("TOKIO KAMIYA", ft1, ty, WHITE), ("TIME-TRAVEL REPORTER", ft2, ty + 52, GOLD)):
        w_ = f_.getbbox(s_)[2] - f_.getbbox(s_)[0]
        tag.append((min(cx - w_ // 2, TW - w_ - 16), y_, s_, f_, col, 3))
    img = Image.alpha_composite(img, text_layer((TW, TH), tag))

    # ラベル（左上）
    d = ImageDraw.Draw(img)
    fb = ImageFont.truetype(FONT_JA_BOLD, 34)
    bw = fb.getbbox(BADGE)[2] + 44
    d.rounded_rectangle((40, 36, 40 + bw, 36 + 62), radius=14, fill=GOLD)
    d.text((62, 44), BADGE, font=fb, fill=(25, 20, 10, 255))

    # キャッチコピー（左、2行。2行目を大きく黄色で）
    max_w = 700  # コピーは左側に収め、主役の顔にかからないようにする
    f1 = fit_font(FONT_JA_HEAVY, COPY_1, max_w, 84)
    f2 = fit_font(FONT_JA_HEAVY, COPY_2, max_w, 190)
    y1 = 130
    y2 = y1 + f1.size + 18
    items = [(44, y1, COPY_1, f1, WHITE, 7), (36, y2, COPY_2, f2, YELLOW, 10)]
    img = Image.alpha_composite(img, text_layer((TW, TH), items))

    # 本編の英文を少しだけ見せる（英語の教材だと一目で分かるように）
    en = f"“{promo['thumb_en']}”"
    fe = fit_font(FONT_EN, en, max_w - 40, 52, index=0)
    ey = y2 + f2.size + 40
    ew = fe.getbbox(en)[2] + 48
    box = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle((40, ey, 40 + ew, ey + fe.size + 34), radius=16, fill=(0, 0, 0, 170))
    img = Image.alpha_composite(img, box)
    img = Image.alpha_composite(img, text_layer((TW, TH), [(64, ey + 12, en, fe, WHITE, 2)]))

    # 題材（左下）
    ft = fit_font(FONT_JA_BOLD, lesson["title_ja"], max_w, 40)
    img = Image.alpha_composite(img, text_layer((TW, TH), [(44, TH - ft.size - 40, lesson["title_ja"], ft, WHITE, 4)]))

    out_local = work / f"{ep_id}_learning_thumbnail.png"
    img.convert("RGB").save(out_local)
    out = DRIVE / ep_id / "learning" / out_local.name
    out.write_bytes(out_local.read_bytes())
    print(f"✅ サムネイル: {out}")


# ---- ショート動画（縦型 1080x1920）
SW, SH = 1080, 1920
FPS = 24
COUNTDOWN = 3          # 考える時間（秒）。懐中時計の秒針の音を1秒ごとに鳴らす
SHORT_TOKIO_H = 0.45   # Tokio の高さ（縦型の画面の高さ 1920 に対する比。約860px）
COLOR_EN = "&HFFFFFF&"
COLOR_JA = "&H8AE0FF&"
COLOR_YEL = "&H00D4FF&"
COLOR_HL = "&HFFC84B&"
COLOR_GOLD = "&H6EC8F0&"
CTA_LINK = "▶ 本編（{m}分）は関連動画から"


def tick_sound(path: Path):
    """懐中時計の秒針のような、短いカチッという音（外部素材は使わない）。"""
    if not path.exists():
        run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             "aevalsrc='0.6*sin(2*PI*2600*t)*exp(-t*90)+0.3*sin(2*PI*5200*t)*exp(-t*140)':s=24000:d=0.12",
             "-ac", "1", "-c:a", "pcm_s16le", path])
    return path


def cmd_short(ep_id: str):
    import wave
    sys.path.insert(0, str(SC_DIR))
    import sc_video_gen as vg
    from build_lesson import ja_audio, ja_tempo, fade_edges, SAMPLE_RATE
    from build_video import ewrap, jwrap, highlight, esc, EN_CHAR_W, JA_CHAR_W
    from clips import _clip_path, split_sentences
    from words import word_times

    lesson = load(ep_id)
    sp = lesson["promo"]["short"]
    dmap = lesson.get("display_map", {})

    def disp(t):
        for k in sorted(dmap, key=len, reverse=True):
            t = t.replace(k, dmap[k])
        return t

    work = BASE_DIR / "build" / ep_id / "short"
    work.mkdir(parents=True, exist_ok=True)
    episode = json.loads((SC_DIR / "episodes" / f"{ep_id}.json").read_text(encoding="utf-8"))
    sc = next(x for x in episode["scenes"] if x["scene_id"] == sp["scene"])
    en_text = split_sentences(sc["narration"])[sp["idx"]]
    clip = _clip_path(DRIVE / ep_id / "audio" / f"S{sp['scene']:02d}.wav", en_text)
    if not clip.exists():
        print(f"英文の切り出しがありません（先に build_lesson.py を実行）: {clip}")
        sys.exit(1)
    words = word_times(clip, en_text)
    _trs = next(s for s in lesson["scenes"] if s["scene"] == sp["scene"])["sentences"]
    _k = sp["idx"]
    while _k > 0 and _trs[_k] is None:   # 訳が null の文は、まとまりの先頭の訳を使う
        _k -= 1
    ja_tr = _trs[_k]
    total_min = round(json.loads((BASE_DIR / "build" / ep_id / "timeline.json").read_text())["total"] / 60)
    cta_ja = f"この続きは、{total_min}分の本編で。日本史を聴くだけで、英語耳になります。本編は、関連動画からどうぞ。"

    # 音声の並び（日本語は本編と同じく、読みの確認をしてから 1.1 倍速にする）
    lines = {k: ja_tempo(ja_audio(t)) for k, t in (("quiz", sp["quiz_ja"]), ("explain", sp["explain_ja"]), ("cta", cta_ja))}
    tick = tick_sound(work / "tick.wav")
    seq, events = [], {}

    def gap(sec):
        seq.append(("gap", sec, None))

    def audio(p, key):
        seq.append(("audio", p, key))

    gap(0.6)                      # Tokio が現れ始めてから話す
    audio(lines["quiz"], "quiz")
    gap(0.4)
    for i in range(COUNTDOWN):    # 考える時間
        audio(tick, f"tick{i}")
        gap(1.0 - 0.12)
    audio(clip, "answer")
    gap(0.8)
    audio(lines["explain"], "explain")
    gap(0.6)
    audio(clip, "replay")
    gap(0.9)
    audio(lines["cta"], "cta")
    gap(2.0)

    wav = work / "short.wav"
    t = 0.0
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for kind, val, key in seq:
            if kind == "gap":
                n = int(val * SAMPLE_RATE)
                out.writeframes(b"\x00\x00" * n)
                t += n / SAMPLE_RATE
            else:
                with wave.open(str(val)) as w:
                    out.writeframes(fade_edges(w.readframes(w.getnframes())))
                    d = w.getnframes() / SAMPLE_RATE
                events[key] = (t, t + d)
                t += d
    total = t

    # ---- 字幕（ASS）
    def at(s):
        cs = int(round(s * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    ev = []

    def add(a, b, text, layer=1):
        ev.append(f"Dialogue: {layer},{at(a)},{at(b)},Base,,0,0,0,,{text}")

    def box(a, b, x0, y0, x1, y1, alpha="60"):
        add(a, b, f"{{\\an7\\pos(0,0)\\p1\\1c&H000000&\\1a&H{alpha}&\\bord0\\shad0}}m {x0} {y0} l {x1} {y0} {x1} {y1} {x0} {y1}{{\\p0}}", 0)

    def en_block(s, e, y, size=68, hl=True):
        le = ewrap(en_text, int((SW - 120) / (size * EN_CHAR_W)))
        base = f"\\fnAvenir Next\\fs{size}\\b1\\c{COLOR_EN}"
        body = highlight(le, words, base) if hl else "\\N".join(le)
        lj = jwrap(esc(disp(ja_tr)), int((SW - 120) / (52 * JA_CHAR_W)))
        box(s, e, 30, y - 30, SW - 30, y + len(le) * size + len(lj) * 56 + 60)
        add(s, e, f"{{\\an8\\pos({SW // 2},{y})}}{{{base}}}{body}\\N{{\\r\\fs16}} \\N"
                  f"{{\\r\\fnHiragino Sans\\fs52\\c{COLOR_JA}}}" + "\\N".join(lj))

    q0, q1 = events["quiz"]
    a0, a1 = events["answer"]
    x0, x1 = events["explain"]
    r0, r1 = events["replay"]
    c0, c1 = events["cta"]
    badge = f"{{\\an8\\pos({SW // 2},90)\\fnHiragino Sans\\b1\\fs50\\c{COLOR_GOLD}\\bord4}}{BADGE}"
    add(0, total, badge)
    # 1) 問い
    add(0.2, a0, f"{{\\an8\\pos({SW // 2},230)\\fnHiragino Sans\\b1\\fs84\\c{COLOR_EN}\\bord6}}{esc(sp['quiz_title'])}\\N"
                 f"{{\\fs150\\c{COLOR_YEL}\\bord9}}英語で言える？")
    # 2) カウントダウン
    for i in range(COUNTDOWN):
        s0, _ = events[f"tick{i}"]
        add(s0, s0 + 0.95, f"{{\\an5\\pos({SW // 2},800)\\fnAvenir Next\\b1\\fs300\\c{COLOR_EN}\\bord10}}{COUNTDOWN - i}")
    # 3) 答え（英文＋訳、単語ハイライト）→ 4) 表現のカードと解説 → 5) もう一度
    add(a0, r1 + 0.6, f"{{\\an8\\pos({SW // 2},230)\\fnHiragino Sans\\b1\\fs70\\c{COLOR_YEL}\\bord6}}答え")
    en_block(a0, x0, 520)
    psize = min(96, int((SW - 140) / (len(sp["phrase"]) * EN_CHAR_W)))
    box(x0, r1 + 0.6, 30, 330, SW - 30, 330 + psize + 170, "40")
    add(x0, r1 + 0.6, f"{{\\an8\\pos({SW // 2},360)\\fnAvenir Next\\b1\\fs{psize}\\c{COLOR_EN}}}{esc(sp['phrase'])}\\N"
                      f"{{\\fnHiragino Sans\\fs60\\c{COLOR_JA}}}＝ {esc(disp(sp['phrase_ja']))}")
    lj = jwrap(esc(disp(sp["explain_ja"])), int((SW - 140) / (56 * JA_CHAR_W)))
    add(x0, x1 + 0.3, f"{{\\an8\\pos({SW // 2},720)\\fnHiragino Sans\\fs56\\c{COLOR_EN}\\bord5}}" + "\\N".join(lj))
    add(r0 - 0.5, r1, f"{{\\an8\\pos({SW // 2},640)\\fnHiragino Sans\\b1\\fs52\\c{COLOR_GOLD}\\bord4}}もう一度")
    en_block(r0, r1 + 0.6, 740)
    # 6) 誘導
    box(c0 - 0.3, total, 0, 0, SW, SH, "50")
    add(c0 - 0.3, total, f"{{\\an8\\pos({SW // 2},330)\\fnHiragino Sans\\b1\\fs100\\c{COLOR_EN}\\bord7}}{COPY_1}\\N"
                         f"{{\\fs190\\c{COLOR_YEL}\\bord10}}{COPY_2}")
    link = CTA_LINK.format(m=total_min)
    box(c0 + 0.5, total, 60, 830, SW - 60, 960, "20")
    add(c0 + 0.5, total, f"{{\\an8\\pos({SW // 2},855)\\fnHiragino Sans\\b1\\fs62\\c{COLOR_EN}}}{link}")

    ass = work / "short.ass"
    ass.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {SW}
PlayResY: {SH}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Hiragino Sans,60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,0,8,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ev) + "\n", encoding="utf-8")

    # ---- 背景（縦型の画像をケンバーンズで）＋ Tokio（左下。転送エフェクトで現れて、最後までいる）
    img = DRIVE / ep_id / "images_shorts" / f"S{sp.get('image_scene', 1):02d}.png"
    if not img.exists():
        print(f"縦型の画像がありません: {img}")
        sys.exit(1)
    bg = work / "bg.mp4"
    vg.make_ken_burns(img, bg, total + 0.05, "zoom_in", landscape=False, anchor=(0.5, 0.35))
    vg.TOKIO_MAT_START = 0.2
    # add_tokio_overlay は横型（1920x1080）の画面の大きさで Tokio の高さと名札の位置を計算するので、縦型の大きさに差し替える
    vg.OUTPUT_W, vg.OUTPUT_H = SW, SH
    vg.TOKIO_H_RATIO = SHORT_TOKIO_H
    sides_expr = "neutral"   # ショートは常に neutral。moved などは「話す」と「待機」で姿勢が大きく違い、切り替えで二重に見える（2026-10-24）
    expr = f"{sides_expr}_talk" if (vg.TOKIO_CLIP_DIR / f"tokio_{sides_expr}_talk.webm").exists() else sides_expr
    bg_idle = work / "bg_idle.mp4"
    shutil.copyfile(bg, bg_idle)          # 重ねる前の背景を取っておく（日本語のセリフ以外は、黙っている Tokio に切り替える）
    glow = bool(episode.get("tokio_glow"))
    vg.add_tokio_overlay(bg, expr, "left", name_tag=True, dur=total, fx_in=True, fx_out=False, glow=glow)
    vg.add_tokio_overlay(bg_idle, sides_expr, "left", name_tag=True, dur=total, fx_in=True, fx_out=False, glow=glow)
    # 1・2・3 の合図の間は、Tokio は話さない（口パクが不自然との指摘。2026-10-24）。問いを言い終えてから、答えの英文が流れるまで
    # さらに、Tokio が話すのは日本語のセリフ（問い・解説・案内）の間だけにする。英文の答えやもう一度の間は待機の動きに戻す（2026-10-24）。
    # 切り替えは、話す映像と待機の映像を 0.25 秒かけて混ぜる（ぱっと入れ替えると不自然なため）。最初は登場の効果があるので、話す映像から始める
    talk = [(-1.0, events["quiz"][1])] + [events[k] for k in ("explain", "cta")]
    tw = "+".join(f"clip((T-{a - 0.1:.3f})/0.25,0,1)*clip(({b + 0.15:.3f}-T)/0.25,0,1)" for a, b in talk)
    mix_expr = f"A*({tw})+B*(1-({tw}))"

    out_local = work / f"{ep_id}_learning_short.mp4"
    sfx_ms = int(vg.TOKIO_MAT_START * 1000)
    run(["ffmpeg", "-y", "-i", bg, "-i", bg_idle, "-i", wav, "-i", vg._tokio_sfx("in"),
         "-filter_complex",
         f"[0:v]format=yuv420p[ta];[1:v]format=yuv420p[ti];[ta][ti]blend=all_expr='{mix_expr}'[w];"
         f"[w]ass=short.ass[v];[2:a]aformat=sample_rates=44100:channel_layouts=stereo,"
         f"loudnorm=I=-14:TP=-1.5:LRA=11[m];[3:a]aformat=sample_rates=44100:channel_layouts=stereo,"
         f"adelay={sfx_ms}|{sfx_ms},volume=0.45[s];[m][s]amix=inputs=2:normalize=0:duration=first[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",  # loudnorm は内部でレートを上げるので、必ず 44.1kHz に戻す（96kHz のままだとスマホで鳴らないことがある）
         "-movflags", "+faststart", out_local], cwd=work)
    out = DRIVE / ep_id / "learning" / out_local.name
    out.write_bytes(out_local.read_bytes())
    print(f"✅ ショート（{total:.1f}秒）: {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("thumb", "short"):
        print(__doc__)
        sys.exit(1)
    {"thumb": cmd_thumb, "short": cmd_short}[sys.argv[1]](sys.argv[2])
