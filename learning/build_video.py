"""学習版の動画を作る: シーンの画像に、英文と日本語訳の字幕を載せて mp4 にする。

入力: build_lesson.py が出力した build/{ep}/timeline.json と、音声版の mp3、
      Drive の ep{NNN}/images/S01〜（シーン画像）
出力: Drive の ep{NNN}/learning/ep{NNN} {日本語タイトル}.mp4

使い方:
  python3 build_video.py ep106                 全編を作る
  python3 build_video.py ep106 --preview 3:30 6:30   指定した範囲だけ作る（字幕の見た目の確認用）

字幕の方針:
  日本語の字幕は、台本の display_map で、ナレーション用のひらがなを漢字に戻して表示する
  解説パート: 合図の音と同時に日本語の訳が出て、英語が始まると、その上に英文が加わる（次の合図まで残る）
  通し: 英文だけを、文ごとに出す
  導入・予告・締め: 日本語を、文ごとに出す（文の時刻は、文字数の比率で割り振る）
"""
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # sc_video_gen（Tokio の合成）を使う

BASE_DIR = Path(__file__).parent
DRIVE = Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles"

W, H = 1920, 1080
FPS = 24
BAND_H = 540   # 画面下の、字幕を載せる暗い帯の高さ
TEXT_W = 1740  # 字幕に使える幅（左右に90pxずつ余白）
TEXT_H = 460   # 帯の中で、字幕に使える高さ
FONT_JA = "Hiragino Sans"
FONT_EN = "Avenir Next"
# 文字サイズの候補（大きい順）。スマホの縦持ち（画面幅の約1/5に縮む）でも読めるよう、大きめにし、
# 長い文だけ、収まる大きさまで自動で下げる。
TIERS_PAIR = [(88, 68), (80, 62), (72, 56), (64, 50), (56, 44)]  # 英語+日本語（英語, 日本語）
TIERS_JA = [84, 76, 68, 60]   # 日本語だけ
TIERS_EN = [96, 88, 80, 72, 64]   # 英語だけ
EN_CHAR_W = 0.45   # 英語1文字の平均の幅（文字サイズに対する比。Avenir Next 太字の実測 約0.36 に余裕を持たせた値）
JA_CHAR_W = 0.82   # 日本語1文字の幅（Hiragino Sans の実測 約0.78 に余裕を持たせた値）
LINE_H = 1.05      # 行の高さ（文字サイズに対する比。libass の実測はほぼ 1.0）
COLOR_EN = "&HFFFFFF&"   # 白（ASS は BGR の並び）
COLOR_JA = "&H8AE0FF&"   # 淡い黄色
COLOR_LABEL = "&H6EC8F0&"  # 金色
COLOR_HL = "&HFFC84B&"     # 話している英単語のハイライト（水色。訳の黄色・ラベルの金色と区別する）
LABEL_SIZE = 44
# Tokio を登場させる（SC 本編と同じ素材・エフェクト・効果音・置く側を sc_video_gen から流用）
TOKIO_MAT_START = 0.3        # 登場エフェクトの開始（秒）。冒頭の間（build_lesson の GAP_OPENING=3秒）のうちに現れ終わる
TOKIO_STAY_AFTER = 0.6       # 自己紹介の段落が終わってから、退場を始めるまでの間（秒）
TOKIO_TEXT_ML = 70           # Tokio がいる間の字幕の余白。Tokio と反対側は狭く、Tokio の側は広く空ける
TOKIO_TEXT_MR = 600
SFX_VOL = 0.45
OUTRO_DUR = 8.0  # 最後のロゴ（本編のアウトロと同じ尺・見せ方。学習版はロゴのみで、英語の投稿予定の文は入れない）
LOGO_W = 330
KB_WORKERS = 4  # ケンバーンズの動画を並列で作る数
# ONE POINT のカード（画面上部の、半透明の黒い板）
CARD_Y = 90
CARD_H = 380
def card_box(x0: int, x1: int) -> str:
    return (f"{{\\an7\\pos(0,0)\\p1\\1c&H000000&\\1a&H40&\\bord0\\shad0}}"
            f"m {x0} {CARD_Y} l {x1} {CARD_Y} {x1} {CARD_Y + CARD_H} {x0} {CARD_Y + CARD_H}{{\\p0}}")
CRF = 24


def run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit(1)


def ass_time(sec: float) -> str:
    cs = int(round(sec * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


DISPLAY_MAP: dict = {}  # 台本の display_map（ナレーション用のひらがな → 字幕用の漢字）。main() で読み込む


def disp(text: str) -> str:
    """ナレーション用にひらがなにした語を、字幕用の表記（漢字）に戻す。長い語から順に置き換える。"""
    for k in sorted(DISPLAY_MAP, key=len, reverse=True):
        text = text.replace(k, DISPLAY_MAP[k])
    return text


def esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


PARTICLES = "をにでがはとのもへや"


def _is_hira(c: str) -> bool:
    return "ぁ" <= c <= "ゖ"


def _is_word_start(c: str) -> bool:
    return ("一" <= c <= "鿿") or ("ァ" <= c <= "ヺ") or c.isascii()


def _soft_break(ch: str, limit: int) -> int:
    """limit 文字以内で、単語の途中にならない切れ目のいちばん後ろの位置を返す。
    優先1: 助詞の直後に漢字・カタカナ・英数字が来る位置（「一緒に｜読み解き」）
    優先2: ひらがなの直後に漢字・カタカナが来る位置（ただし「読み｜解き」のような送り仮名でも切れてしまう）
    優先3: 助詞の直後（「ながら」の「が」のような取り違えがある）
    行が短くなりすぎる位置（limit の半分以下）は使わない。見つからなければ limit。"""
    rng = range(min(limit, len(ch) - 1), limit // 2, -1)
    rules = (
        lambda a, b: a in PARTICLES and _is_word_start(b),
        lambda a, b: _is_hira(a) and _is_word_start(b),
        lambda a, b: a in PARTICLES and b not in PARTICLES,
    )
    for ok in rules:
        for i in rng:
            if ok(ch[i - 1], ch[i]):
                return i
    return limit


def jwrap(text: str, limit: int) -> list:
    """日本語を、句読点の切れ目をなるべく使って、limit 文字以内の行に折り返す（libass は、スペースのない日本語を自動では折り返さない）。"""
    chunks = re.findall(r"[^、。]+[、。]?|[、。]", text)
    lines, cur = [], ""
    for ch in chunks:
        while len(ch) > limit:  # 句読点なしで長い塊は、助詞の後ろで切る（なければ limit で切る）
            if cur:
                lines.append(cur)
                cur = ""
            cut = _soft_break(ch, limit)
            lines.append(ch[:cut])
            ch = ch[cut:]
        if len(cur) + len(ch) <= limit:
            cur += ch
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def highlight(lines: list[str], words: list[dict], base: str) -> str:
    """折り返し済みの英文の各単語に、話している間だけ色を変える指定を付ける（\\t で瞬時に色を切り替える）。
    words は台本の単語と同じ並びで、時刻はこの字幕の表示開始からの秒。
    ASS の指定は後ろの文字に引き継がれるので、単語ごとに \\r でリセットしてから base（書体・大きさ・色）を指定し直す。"""
    toks = [w for line in lines for w in line.split()]
    if len(toks) != len(words):  # 並びが合わない（想定外）ときは、ハイライトなしで出す
        return "\\N".join(lines)
    out, k = [], 0
    for line in lines:
        segs = []
        for w in line.split():
            a = int(words[k]["s"] * 1000)
            nxt = words[k + 1]["s"] if k + 1 < len(words) else words[k]["e"] + 0.2
            b = int(min(nxt, words[k]["e"] + 0.3) * 1000)  # 次の単語が始まるまで（長い間では 0.3 秒で戻す）
            segs.append(f"{{\\r{base}\\t({a},{a + 1},\\1c{COLOR_HL})\\t({b},{b + 1},\\1c{COLOR_EN})}}{w}")
            k += 1
        out.append(" ".join(segs))
    return "\\N".join(out)


def ewrap(text: str, limit: int) -> list[str]:
    """英語を、単語の区切りで limit 文字以内の行に折り返す。"""
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > limit:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def fit(en, ja, translation=False, width=None, words=None) -> str:
    """英語・日本語（片方だけでもよい）を、帯に収まる最大の文字サイズで折り返し、ASS の文字列にして返す。
    translation=True のときは、英語がなくても日本語を訳の色（黄色）にする（英語が出る前後で色が変わらないように）。"""
    width = width or TEXT_W
    if en and ja:
        tiers = TIERS_PAIR
    elif ja:
        tiers = [(0, t) for t in TIERS_JA]
    else:
        tiers = [(t, 0) for t in TIERS_EN]
    for se, sj in tiers:
        le = ewrap(en, int(width / (se * EN_CHAR_W))) if en else []
        lj = jwrap(ja, int(width / (sj * JA_CHAR_W))) if ja else []
        gap = int(se * 0.3) if le and lj else 0
        h = len(le) * se * LINE_H + len(lj) * sj * LINE_H + gap
        if h <= TEXT_H:
            break
    parts = []
    if le:
        base = f"\\fn{FONT_EN}\\fs{se}\\b1\\c{COLOR_EN}"
        body = "\\N".join(le) if not words else highlight(le, words, base)
        parts.append(f"{{{base}}}" + body)
    if le and lj:
        parts.append(f"{{\\r\\fs{gap}}} ")
    if lj:
        c = COLOR_JA if (en or translation) else COLOR_EN  # 訳は黄色、導入・予告などの日本語は白
        parts.append(f"{{\\r\\fn{FONT_JA}\\fs{sj}\\b0\\c{c}}}" + "\\N".join(lj))
    return "\\N".join(parts)


def split_timed(text: str, start: float, end: float) -> list[tuple[str, float, float]]:
    """日本語の長い文章を「。」で区切り、文字数の比率で時刻を割り振る（強制アライメントではない近似）。"""
    parts = [p for p in re.findall(r"[^。]+。?", text) if p.strip()]
    total = sum(len(p) for p in parts) or 1
    out, t = [], start
    for p in parts:
        d = (end - start) * len(p) / total
        out.append((p, t, t + d))
        t += d
    return out


REVERSE = {"zoom_in": "zoom_out", "zoom_out": "zoom_in", "pan_left": "pan_right", "pan_right": "pan_left",
           "pan_zoom_out_lr": "pan_zoom_out_rl", "pan_zoom_out_rl": "pan_zoom_out_lr"}


def kb_plan(episode: dict, scene_id: int, second: bool):
    """シーンのケンバーンズの動き（effect）と注目点（px, py）を、本編の動画と同じ決め方で返す。
    infer_zoom_anchor は複数人の画像で左右のパンをランダムに選ぶので、シーン番号で乱数を固定する（作り直しても同じ動き）。"""
    import random
    import sc_video_gen as vg
    sc = next(x for x in episode["scenes"] if x["scene_id"] == scene_id)
    random.seed(scene_id)
    px, py, override = vg.infer_zoom_anchor(sc.get("image_prompt", ""), sc.get("character_ref"), sc.get("zoom_anchor"))
    effect = override or sc.get("ken_burns", "zoom_in")
    if effect == "static":
        effect = "zoom_in"
    if second:
        effect = REVERSE.get(effect, effect)
    return effect, (px, py)


def build_ass(tl: dict, window=None, tokio_windows=()) -> tuple[str, list[tuple[float, float, str]]]:
    """字幕（ASS）と、画像の切り替え表（開始, 終了, 画像名）を作る。
    window=(開始, 終了) のときは、その範囲だけを 0 秒始まりに直して返す（プレビュー用）。
    tokio_windows=[(開始, 終了, 'left'|'right'), ...] は Tokio が画面に出る区間。その間の字幕とカードは反対側に寄せる。"""
    ev = tl["events"]
    total = tl["total"]
    lines: list[str] = []
    w0, w1 = window or (0.0, total)

    def clip(start, end):
        return max(start, w0) - w0, min(end, w1) - w0

    def add(start, end, text, style="Text", ml=0, mr=0, layer=0):
        start, end = clip(start, end)
        if end - start < 0.05:
            return
        lines.append(f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,{ml},{mr},0,,{text}")

    def side_at(t):
        return next((sd for a, b, sd in tokio_windows if a <= t < b), None)

    def text(start, end, en, ja, translation=False, words=None):
        """画面下の帯に字幕を置く。Tokio がいる間は、Tokio と反対側に寄せて狭い幅で折り返す。"""
        sd = side_at(start)
        ml, mr = {"right": (TOKIO_TEXT_ML, TOKIO_TEXT_MR), "left": (TOKIO_TEXT_MR, TOKIO_TEXT_ML)}.get(sd, (0, 0))
        add(start, end, fit(en, ja, translation, width=(W - ml - mr) if sd else None, words=words), ml=ml, mr=mr)

    scenes = sorted({e["scene"] for e in ev if "scene" in e})
    n_scenes = len(scenes)

    def cue_of(n):
        return next(e for e in ev if e["kind"] == "cue" and e["scene"] == n)

    to_full = next(e for e in ev if e["kind"] == "to_full")
    closing = next(e for e in ev if e["kind"] == "closing")
    first_cue = cue_of(scenes[0])
    # 各シーンの解説パートの終わり = 次のシーンの予告の開始（最後のシーンは通しの案内の開始）
    scene_end = {n: (cue_of(scenes[i + 1])["start"] if i + 1 < n_scenes else to_full["start"]) for i, n in enumerate(scenes)}

    # ---- 導入
    for e in ev:
        if e["kind"] == "intro":
            for line, s, t in split_timed(e["text"], e["start"], e["end"]):
                text(s, t, None, esc(disp(line)))

    # ---- シーンごとの解説パート
    for n in scenes:
        c = cue_of(n)
        label = f"SCENE {n} / {n_scenes}"
        add(c["start"], scene_end[n], f"{{\\an7\\pos(60,40)\\fs{LABEL_SIZE}\\c{COLOR_LABEL}}}{label}", "Label")
        text(c["start"], c["end"] + 0.8, None, esc(disp(c["text"])))
        evs = [e for e in ev if e.get("scene") == n and e["kind"] in ("chime", "ja", "en")]
        # 文ごとの組: chime → ja → en（訳のない文は en だけ）
        by_idx: dict[int, dict] = {}
        for e in evs:
            by_idx.setdefault(e["idx"], {})[e["kind"]] = e
        idxs = sorted(by_idx)
        op = next((e for e in ev if e["kind"] == "op" and e["scene"] == n), None)
        op_en = next((e for e in ev if e["kind"] == "op_en" and e["scene"] == n), None)
        pairs_end = op["start"] if op else scene_end[n]
        for k, i in enumerate(idxs):
            g = by_idx[i]
            nxt = by_idx[idxs[k + 1]] if k + 1 < len(idxs) else None
            # 次の組が始まる時刻（合図の音があればその開始、なければ英語の開始）で、この組を消す
            until = (nxt["chime"]["start"] if nxt and "chime" in nxt else nxt["en"]["start"]) if nxt else pairs_end
            ja_txt = esc(disp(g["ja"]["text"])) if "ja" in g else None
            en_txt = esc(g["en"]["text"])
            if ja_txt:
                # 合図の音と同時に訳を出す。英語が始まったら、その上に英文を足す
                text(g["chime"]["start"], g["en"]["start"], None, ja_txt, translation=True)
                text(g["en"]["start"], until, en_txt, ja_txt, words=g["en"].get("words"))
            else:
                text(g["en"]["start"], until, en_txt, None, words=g["en"].get("words"))

        if op:
            # ONE POINT のカード（画面の上部）: 見出し・表現・意味。解説とその英文が終わるまで出しておく
            card_end = (op_en["end"] if op_en else op["end"]) + 0.6
            # Tokio がいる間は、カードを Tokio と反対側に寄せて幅を狭める（頭がカードに隠れないように）
            sd = side_at(op["start"])
            x0, x1 = {"right": (120, W - 580), "left": (580, W - 120)}.get(sd, (200, W - 200))
            add(op["start"], card_end, card_box(x0, x1), "Card", layer=0)
            psize = 120 if len(op["phrase"]) <= 22 else (104 if len(op["phrase"]) <= 28 else 92)
            psize = min(psize, int((x1 - x0 - 60) / (len(op["phrase"]) * EN_CHAR_W)))  # カードの幅に収める
            add(op["start"], card_end,
                f"{{\\an8\\pos({(x0 + x1) // 2},{CARD_Y + 30})\\fn{FONT_EN}\\b1\\fs54\\c{COLOR_LABEL}}}ONE POINT\\N"
                f"{{\\fs{psize}\\c{COLOR_EN}}}{esc(op['phrase'])}\\N"
                f"{{\\fn{FONT_JA}\\b0\\fs76\\c{COLOR_JA}}}{esc(disp(op['phrase_ja']))}", "Label", layer=1)
            for line, s0, t0 in split_timed(op["text"], op["start"], op["end"]):
                text(s0, t0, None, esc(disp(line)))
            if op_en:
                text(op_en["start"], op_en["end"] + 0.6, esc(op_en["text"]), None, words=op_en.get("words"))

    # ---- 通し
    for line, s, t in split_timed(to_full["text"], to_full["start"], to_full["end"]):
        text(s, t, None, esc(disp(line)))
    fulls = sorted((e for e in ev if e["kind"] == "full_scene"), key=lambda e: e["start"])
    for fi, e in enumerate(fulls):
        end_scene = fulls[fi + 1]["start"] if fi + 1 < len(fulls) else closing["start"]
        add(e["start"], end_scene, f"{{\\an7\\pos(60,40)\\fs{LABEL_SIZE}\\c{COLOR_LABEL}}}LISTEN  /  SCENE {e['scene']}", "Label")
        sens = e["sentences"]
        for k, sen in enumerate(sens):
            until = sens[k + 1]["start"] if k + 1 < len(sens) else e["end"] + 0.5
            text(sen["start"], until, esc(sen["text"]), None, words=sen.get("words"))

    # ---- 締め
    for line, s, t in split_timed(closing["text"], closing["start"], closing["end"]):
        text(s, t, None, esc(disp(line)))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Text,{FONT_JA},60,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,0,2,90,90,50,1
Style: Card,{FONT_JA},20,&H00000000,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Label,{FONT_JA},{LABEL_SIZE},{COLOR_LABEL},&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,7,60,60,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # ---- 画像の切り替え: 各シーンはそのシーンの画像。導入と通しの案内は最初のシーン、締めは最後のシーンの画像
    # （サムネイルは英語のタイトル文字が入っていて、日本語の字幕と重なるので使わない）
    first_img, last_img = f"S{scenes[0]:02d}", f"S{scenes[-1]:02d}"
    segs: list[tuple[float, float, str]] = [(0.0, first_cue["start"], first_img)]
    for n in scenes:
        segs.append((cue_of(n)["start"], scene_end[n], f"S{n:02d}"))
    segs.append((to_full["start"], fulls[0]["start"], first_img))
    for fi, e in enumerate(fulls):
        end_scene = fulls[fi + 1]["start"] if fi + 1 < len(fulls) else closing["start"]
        segs.append((e["start"], end_scene, f"S{e['scene']:02d}"))
    segs.append((closing["start"], total, last_img))
    segs = [(*clip(s, e), name) for s, e, name in segs]
    segs = [(s, e, name) for s, e, name in segs if e - s > 0.001]
    return header + "\n".join(lines) + "\n", segs


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    ep_id = args[0]
    preview = None
    if "--preview" in args:
        i = args.index("--preview")

        def sec(x):
            m, s = x.split(":")
            return int(m) * 60 + float(s)

        preview = (sec(args[i + 1]), sec(args[i + 2]))

    work = BASE_DIR / "build" / ep_id
    tl = json.loads((work / "timeline.json").read_text(encoding="utf-8"))
    lesson = json.loads((BASE_DIR / "lessons" / f"{ep_id}.json").read_text(encoding="utf-8"))
    DISPLAY_MAP.update(lesson.get("display_map", {}))
    ep_dir = DRIVE / ep_id
    audio = work / f"{ep_id} {tl['title_ja']}.mp3"  # 音声版と同じ（音量をそろえ済み。build_lesson.py が手元に置く）
    for p in (audio, ep_dir / "images" / "S01.png"):
        if not p.exists():
            print(f"素材がありません: {p}")
            sys.exit(1)

    import sc_video_gen as vg
    episode = json.loads((BASE_DIR.parent / "episodes" / f"{ep_id}.json").read_text(encoding="utf-8"))
    ev = tl["events"]
    total = tl["total"]
    out_pad = vg.CROSSFADE_DURATION + vg.TOKIO_OUT_DUR + 0.2   # add_tokio_overlay は「終わりの out_pad 秒前」に退場を始める

    # Tokio が出る区間（ユーザー決定: 冒頭の自己紹介・解説パートの締め（最後のシーン）・通しの最初と最後〜締めの挨拶）
    intro0 = next(e for e in ev if e["kind"] == "intro")
    cues = sorted((e for e in ev if e["kind"] == "cue"), key=lambda e: e["start"])
    to_full = next(e for e in ev if e["kind"] == "to_full")
    fulls = sorted((e for e in ev if e["kind"] == "full_scene"), key=lambda e: e["start"])
    windows = [
        dict(a=0.0, b=intro0["end"] + TOKIO_STAY_AFTER + out_pad, sid=cues[0]["scene"], tag=True),
        dict(a=cues[-1]["start"], b=to_full["start"], sid=cues[-1]["scene"], tag=False),
        dict(a=fulls[0]["start"], b=fulls[1]["start"], sid=fulls[0]["scene"], tag=False),
        dict(a=fulls[-1]["start"], b=total, sid=fulls[-1]["scene"], tag=False),
    ]
    sides = vg.tokio_sides(episode, episode["scenes"])
    for w in windows:  # 本編と同じ側（被写体の反対側）・同じ表情。話すループがあればそれを使う
        sc = next(x for x in episode["scenes"] if x["scene_id"] == w["sid"])
        expr = sc.get("tokio_expression", "neutral")
        w["expr"] = f"{expr}_talk" if (vg.TOKIO_CLIP_DIR / f"tokio_{expr}_talk.webm").exists() else expr
        w["side"] = sides.get(w["sid"], "right")

    if preview and preview[0] < windows[0]["b"]:
        preview = (0.0, max(preview[1], windows[0]["b"] + 1.0))  # 冒頭の Tokio を含むプレビューは、冒頭から作る
    t0, t1 = preview or (0.0, total)
    wins = [w for w in windows if w["a"] >= t0 and w["b"] <= t1]  # プレビューでは、範囲に収まる区間だけ

    ass_text, _ = build_ass(tl, preview, tokio_windows=[(w["a"], w["b"], w["side"]) for w in wins])
    (work / "subs.ass").write_text(ass_text, encoding="utf-8")

    # 画像の表（全体の時刻）。同じ画像が続く区間は1つにまとめ、つながった1本の動きにする
    # （区間ごとに動きを作ると、同じ画像なのに境目で拡大率が飛ぶ。冒頭→導入→シーン1、通しの案内→通しのシーン1 など）
    _, segs = build_ass(tl, (t0, t1))
    runs: list = []
    for s, e, name in segs:
        a, b = s + t0, e + t0
        if runs and runs[-1][0] == name and abs(runs[-1][2] - a) < 0.01:
            runs[-1][2] = b
        else:
            runs.append([name, a, b])

    # 画像を 1920x1080 にそろえる（元は 1408x768 など。中央を基準に切り出す）
    frames = work / "frames"
    frames.mkdir(exist_ok=True)
    for name in {r[0] for r in runs}:
        run(["ffmpeg", "-y", "-i", str(ep_dir / "images" / f"{name}.png"), "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-q:v", "2", str(frames / f"{name}.jpg")])

    # 背景: 各まとまりを、本編と同じケンバーンズ（ゆっくりした拡大・移動）の動画にする（4本並列。作ったものは使い回す）
    def F(x):  # 全体の時刻 → コマ番号（境目をすべて全体の時刻でコマにそろえ、ずれが積み重ならないようにする）
        return round(x * FPS)

    kb_dir = work / "kb"
    kb_dir.mkdir(exist_ok=True)
    seen: dict = {}
    jobs = []
    for name, a, b in runs:
        second = seen.get(name, 0) > 0  # 同じ画像の2回目（通し）は、逆向きの動きにする
        seen[name] = seen.get(name, 0) + 1
        jobs.append((name, F(b) - F(a), *kb_plan(episode, int(name[1:]), second)))

    def make_kb(job):
        name, n_frames, effect, (px, py) = job
        dst = kb_dir / f"{name}_{effect}_{n_frames}_{px:.2f}_{py:.2f}.mp4"
        if not dst.exists():
            vg.make_ken_burns(frames / f"{name}.jpg", dst, n_frames / FPS + 0.001, effect, anchor=(px, py))
        return dst

    with ThreadPoolExecutor(KB_WORKERS) as ex:
        kb_clips = list(ex.map(make_kb, jobs))

    def cut(clip: Path, f0: int, f1: int) -> Path:
        """クリップの f0〜f1 コマ目を切り出す（作ったものは使い回す）。"""
        dst = kb_dir / f"{clip.stem}_{f0}-{f1}.mp4"
        if not dst.exists():
            run(["ffmpeg", "-y", "-i", str(clip), "-vf", f"trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS",
                 "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(dst)])
        return dst

    # Tokio の区間の境目でケンバーンズを切り分け、区間ごとに Tokio を重ねる（区間の中の背景の動きは、切らずにつながったまま）
    pieces: list = []  # (クリップ, 区間の番号 or None)
    for (name, a, b), clip in zip(runs, kb_clips):
        fa, fb = F(a), F(b)
        cuts = sorted({fa, fb} | {F(w[k]) for w in wins for k in ("a", "b") if fa < F(w[k]) < fb})
        for x, y in zip(cuts, cuts[1:]):
            wi = next((i for i, w in enumerate(wins) if F(w["a"]) <= x and y <= F(w["b"])), None)
            pieces.append((clip if (x, y) == (fa, fb) else cut(clip, x - fa, y - fa), wi))

    band = f"drawbox=x=0:y={H - BAND_H}:w={W}:h={BAND_H}:color=black@0.62:t=fill"
    vg.TOKIO_MAT_START = TOKIO_MAT_START
    final: list = []
    for i, w in enumerate(wins):
        parts = [c for c, wi in pieces if wi == i]
        base = work / f"tokio_{i}_base.mp4"
        if len(parts) == 1:
            src = ["-i", str(parts[0])]
        else:
            lst = work / f"tokio_{i}_parts.txt"
            lst.write_text("".join(f"file '{c}'\n" for c in parts), encoding="utf-8")
            src = ["-f", "concat", "-safe", "0", "-i", str(lst)]
        # 帯を先に描いてから Tokio を重ねる（Tokio が帯で暗くならないように）
        run(["ffmpeg", "-y", *src, "-vf", f"format=yuv420p,{band}", "-c:v", "libx264", "-crf", "18",
             "-preset", "veryfast", "-pix_fmt", "yuv420p", str(base)])
        w["dur"] = (F(w["b"]) - F(w["a"])) / FPS
        vg.add_tokio_overlay(base, w["expr"], w["side"], name_tag=w["tag"], dur=w["dur"])
        w["clip"] = base
    done = set()
    for c, wi in pieces:
        if wi is None:
            final.append(c)
        elif wi not in done:
            final.append(wins[wi]["clip"])
            done.add(wi)
    with_outro = t1 >= total - 0.01  # 最後まで含むときは、ロゴのアウトロを付ける
    if with_outro:
        outro = work / "outro.mp4"
        if not outro.exists():
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0a0a0a:size={W}x{H}:rate={FPS}:d={OUTRO_DUR}",
                 "-i", str(vg.LOGO_PATH), "-filter_complex",
                 f"[1:v]scale={LOGO_W}:-1,format=rgba[logo];[0:v][logo]overlay=(W-w)/2:(H-h)/2,"
                 f"fade=t=in:st=0:d=1.5,fade=t=out:st={OUTRO_DUR - 1.5}:d=1.5,format=yuv420p[v]",
                 "-map", "[v]", "-t", str(OUTRO_DUR), "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", str(outro)])
        final.append(outro)
    concat = work / "images.txt"
    concat.write_text("".join(f"file '{c}'\n" for c in final), encoding="utf-8")

    title = f"{ep_id} {tl['title_ja']}"
    out_dir = ep_dir / "learning"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{title}_preview.mp4" if preview else f"{title}.mp4"
    out = work / out_name  # 手元に作ってから、完成したものだけ Drive にコピーする
    length = t1 - t0 + (OUTRO_DUR if with_outro else 0.0)

    # 帯は Tokio の区間以外に描く（Tokio の区間は、帯を描いてから Tokio を重ねてある）。アウトロ（ロゴ）にも描かない
    off = "+".join(f"between(t,{F(w['a']) / FPS - t0:.3f},{F(w['b']) / FPS - t0:.3f})" for w in wins)
    if with_outro:
        off = (off + "+" if off else "") + f"gte(t,{t1 - t0:.3f})"
    band_rest = band + (f":enable='not({off})'" if off else "")
    # ass は、作業フォルダに置いたファイルを相対で指定する（パスの記号を避けるため）
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-ss", f"{t0:.3f}", "-i", str(audio)]
    fc = f"[0:v]fps={FPS},format=yuv420p,{band_rest},ass=subs.ass[v];[1:a]aformat=sample_rates=44100:channel_layouts=stereo[m]"
    mix = ["[m]"]
    for i, w in enumerate(wins):  # 転送の効果音（登場・退場）を、各区間の時刻に重ねる
        te = max(vg.TOKIO_IN_LEN + 1.0, w["dur"] - out_pad)
        for kind, at in (("in", w["a"] - t0 + TOKIO_MAT_START), ("out", w["a"] - t0 + te)):
            k = len(mix) + 1
            cmd += ["-i", str(vg._tokio_sfx(kind))]
            ms = int(at * 1000)
            fc += f";[{k}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={ms}|{ms},volume={SFX_VOL}[s{k}]"
            mix.append(f"[s{k}]")
    fc += f";{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,apad[a]"  # アウトロの間は無音
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
    # 動画の長さを音声に合わせる（concat の最後の画像が余分に伸びるのを防ぐ）
    cmd += ["-t", f"{length:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work))
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit(1)
    if preview:
        print(f"✅ プレビュー（手元）: {out}  （{t0:.0f}〜{t1:.0f}秒）")
    else:
        shutil.copyfile(out, out_dir / out_name)
        print(f"✅ 完成: {out_dir / out_name}")


if __name__ == "__main__":
    main()
