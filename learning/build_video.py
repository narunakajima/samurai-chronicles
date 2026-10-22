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
# 冒頭の自己紹介で、Tokio を登場させる（SC 本編と同じ素材・エフェクト・効果音を sc_video_gen から流用）
TOKIO_EXPR = "neutral_talk"   # 話すループ（口が動く版）
TOKIO_SIDE = "right"
TOKIO_MAT_START = 0.3        # 登場エフェクトの開始（秒）。冒頭の間（build_lesson の GAP_OPENING=3秒）のうちに現れ終わる
TOKIO_STAY_AFTER = 0.6       # 自己紹介の段落が終わってから、退場を始めるまでの間（秒）
TOKIO_TEXT_ML = 70           # Tokio がいる間の字幕の左右の余白（右側を Tokio に空ける）
TOKIO_TEXT_MR = 600
SFX_VOL = 0.45
# ONE POINT のカード（画面上部の、半透明の黒い板）
CARD_Y = 90
CARD_H = 380
CARD_BOX = (f"{{\\an7\\pos(0,0)\\p1\\1c&H000000&\\1a&H40&\\bord0\\shad0}}"
            f"m 200 {CARD_Y} l {W - 200} {CARD_Y} {W - 200} {CARD_Y + CARD_H} 200 {CARD_Y + CARD_H}{{\\p0}}")
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


def build_ass(tl: dict, window=None, tokio_until: float = 0.0) -> tuple[str, list[tuple[float, float, str]]]:
    """字幕（ASS）と、画像の切り替え表（開始, 終了, 画像名）を作る。
    window=(開始, 終了) のときは、その範囲だけを 0 秒始まりに直して返す（プレビュー用）。"""
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
            for text, s, t in split_timed(e["text"], e["start"], e["end"]):
                if s < tokio_until:  # Tokio（画面の右側）と重ならないよう、左に寄せて狭い幅で折り返す
                    add(s, t, fit(None, esc(disp(text)), width=W - TOKIO_TEXT_ML - TOKIO_TEXT_MR),
                        ml=TOKIO_TEXT_ML, mr=TOKIO_TEXT_MR)
                else:
                    add(s, t, fit(None, esc(disp(text))))

    # ---- シーンごとの解説パート
    for n in scenes:
        c = cue_of(n)
        label = f"SCENE {n} / {n_scenes}"
        add(c["start"], scene_end[n], f"{{\\an7\\pos(60,40)\\fs{LABEL_SIZE}\\c{COLOR_LABEL}}}{label}", "Label")
        add(c["start"], c["end"] + 0.8, fit(None, esc(disp(c["text"]))))
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
                add(g["chime"]["start"], g["en"]["start"], fit(None, ja_txt, translation=True))
                add(g["en"]["start"], until, fit(en_txt, ja_txt, words=g["en"].get("words")))
            else:
                add(g["en"]["start"], until, fit(en_txt, None, words=g["en"].get("words")))

        if op:
            # ONE POINT のカード（画面の上部）: 見出し・表現・意味。解説とその英文が終わるまで出しておく
            card_end = (op_en["end"] if op_en else op["end"]) + 0.6
            add(op["start"], card_end, CARD_BOX, "Card", layer=0)
            psize = 120 if len(op["phrase"]) <= 22 else (104 if len(op["phrase"]) <= 28 else 92)
            add(op["start"], card_end,
                f"{{\\an8\\pos({W // 2},{CARD_Y + 30})\\fn{FONT_EN}\\b1\\fs54\\c{COLOR_LABEL}}}ONE POINT\\N"
                f"{{\\fs{psize}\\c{COLOR_EN}}}{esc(op['phrase'])}\\N"
                f"{{\\fn{FONT_JA}\\b0\\fs76\\c{COLOR_JA}}}{esc(disp(op['phrase_ja']))}", "Label", layer=1)
            for text, s0, t0 in split_timed(op["text"], op["start"], op["end"]):
                add(s0, t0, fit(None, esc(disp(text))))
            if op_en:
                add(op_en["start"], op_en["end"] + 0.6, fit(esc(op_en["text"]), None, words=op_en.get("words")))

    # ---- 通し
    for text, s, t in split_timed(to_full["text"], to_full["start"], to_full["end"]):
        add(s, t, fit(None, esc(disp(text))))
    fulls = sorted((e for e in ev if e["kind"] == "full_scene"), key=lambda e: e["start"])
    for fi, e in enumerate(fulls):
        end_scene = fulls[fi + 1]["start"] if fi + 1 < len(fulls) else closing["start"]
        add(e["start"], end_scene, f"{{\\an7\\pos(60,40)\\fs{LABEL_SIZE}\\c{COLOR_LABEL}}}LISTEN  /  SCENE {e['scene']}", "Label")
        sens = e["sentences"]
        for k, sen in enumerate(sens):
            until = sens[k + 1]["start"] if k + 1 < len(sens) else e["end"] + 0.5
            add(sen["start"], until, fit(esc(sen["text"]), None, words=sen.get("words")))

    # ---- 締め
    for text, s, t in split_timed(closing["text"], closing["start"], closing["end"]):
        add(s, t, fit(None, esc(disp(text))))

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

    # Tokio が出る区間（冒頭〜自己紹介の段落の終わり＋退場エフェクト）
    intro0 = next(e for e in tl["events"] if e["kind"] == "intro")
    import sc_video_gen as vg
    tokio_len = intro0["end"] + TOKIO_STAY_AFTER + vg.CROSSFADE_DURATION + vg.TOKIO_OUT_DUR + 0.2
    tokio_exit = tokio_len - vg.CROSSFADE_DURATION - vg.TOKIO_OUT_DUR - 0.2   # add_tokio_overlay の退場開始と同じ式
    with_tokio = preview is None or preview[0] < tokio_len
    if preview and with_tokio:
        preview = (0.0, max(preview[1], tokio_len + 1.0))  # Tokio の区間を含むプレビューは、冒頭から作る

    t0, t1 = preview or (0.0, tl["total"])
    ass_text, _ = build_ass(tl, preview, tokio_until=tokio_len if with_tokio else 0.0)
    (work / "subs.ass").write_text(ass_text, encoding="utf-8")
    # 画像の表: Tokio の区間は別に作るので、その後ろから
    img_from = tokio_len if with_tokio else t0
    _, segs = build_ass(tl, (img_from, t1))

    # 画像を 1920x1080 にそろえる（元は 1408x768 など。中央を基準に切り出す）
    frames = work / "frames"
    frames.mkdir(exist_ok=True)
    names = {name for _, _, name in segs} | {"S01"}
    for name in names:
        run(["ffmpeg", "-y", "-i", str(ep_dir / "images" / f"{name}.png"), "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-q:v", "2", str(frames / f"{name}.jpg")])

    concat = work / "images.txt"
    rows = []
    for s, e, name in segs:
        rows += [f"file '{frames / (name + '.jpg')}'", f"duration {e - s:.3f}"]
    rows.append(f"file '{frames / (segs[-1][2] + '.jpg')}'")  # concat の仕様で、最後のファイルは繰り返す
    concat.write_text("\n".join(rows) + "\n", encoding="utf-8")

    band = f"drawbox=x=0:y={H - BAND_H}:w={W}:h={BAND_H}:color=black@0.62:t=fill"
    if with_tokio:
        # 冒頭の区間: シーン1の画像＋帯の上に、Tokio（話すループ・転送エフェクト・名札）を重ねたクリップを作る
        tokio_clip = work / "tokio_intro.mp4"
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(frames / "S01.jpg"), "-t", f"{tokio_len:.3f}",
             "-vf", f"fps={FPS},format=yuv420p,{band}", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", str(tokio_clip)])
        vg.TOKIO_MAT_START = TOKIO_MAT_START
        vg.add_tokio_overlay(tokio_clip, TOKIO_EXPR, TOKIO_SIDE, name_tag=True, dur=tokio_len)

    title = f"{ep_id} {tl['title_ja']}"
    out_dir = ep_dir / "learning"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{title}_preview.mp4" if preview else f"{title}.mp4"
    out = work / out_name  # 手元に作ってから、完成したものだけ Drive にコピーする
    length = t1 - t0

    # ass は、作業フォルダに置いたファイルを相対で指定する（パスの記号を避けるため）
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat)]
    if with_tokio:
        cmd += ["-i", str(tokio_clip), "-i", str(audio),
                "-i", str(vg._tokio_sfx("in")), "-i", str(vg._tokio_sfx("out"))]
        d_in = int(TOKIO_MAT_START * 1000)
        d_out = int(tokio_exit * 1000)
        fc = (f"[0:v]fps={FPS},format=yuv420p,{band},setsar=1[rest];"
              f"[1:v]fps={FPS},format=yuv420p,setsar=1[intro];"
              f"[intro][rest]concat=n=2:v=1:a=0,ass=subs.ass[v];"
              f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo[m];"
              f"[3:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={d_in}|{d_in},volume={SFX_VOL}[s1];"
              f"[4:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={d_out}|{d_out},volume={SFX_VOL}[s2];"
              f"[m][s1][s2]amix=inputs=3:normalize=0:duration=first[a]")
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
    else:
        # Tokio の区間を含まないプレビュー: 字幕と画像の表は指定範囲に合わせてあるので、音声だけ指定時刻から読む
        cmd += ["-ss", f"{t0:.2f}", "-i", str(audio), "-vf", f"fps={FPS},format=yuv420p,{band},ass=subs.ass"]
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
