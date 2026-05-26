"""
sc_video_gen.py — Samurai Chronicles 最終動画生成スクリプト

使い方:
  python3 sc_video_gen.py --episode ep001
  python3 sc_video_gen.py --episode ep001 --output ~/Desktop
  python3 sc_video_gen.py --episode ep001 --shorts   # Shorts用クリップのみ生成

処理フロー:
  1. イントロクリップ生成（ロゴ + タイトル）
  2. 各シーン画像に Ken Burns エフェクト（zoom_in/zoom_out/pan_right/pan_left/static）
  3. 各シーンの尺 = ナレーション音声長 + バッファ（最低 duration_seconds）
  4. 全シーンをクロスフェードでつなぐ
  5. アウトロクリップ生成（ロゴ + テキスト）
  6. イントロ + 本編 + アウトロを結合
  7. ナレーション音声（イントロ分オフセット）+ BGM をミックス
  8. 本編 MP4 を output/ に保存
  9. --shorts 時: イントロ + ハイライトシーン + Shorts アウトロを 9:16 で出力

必要ファイル（各ディレクトリ内）:
  images/{episode_id}/S01.png ... S20.png
  audio/{episode_id}/S01.wav  ... S20.wav
  audio/{episode_id}/{episode_id}-BGM.mp3
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).parent  # スクリプト・エピソードJSONの場所

# 生成素材の保存先・読み込み元（Google Drive）
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)

# ── 映像設定 ────────────────────────────────────────────
OUTPUT_W = 1920
OUTPUT_H = 1080
OUTPUT_RES = f"{OUTPUT_W}:{OUTPUT_H}"   # 横長 16:9（本編）
SHORTS_W = 1080
SHORTS_H = 1920
SHORTS_RES = f"{SHORTS_W}:{SHORTS_H}"  # 縦長 9:16（Shorts）
FPS = 24
CROSSFADE_DURATION = 0.8   # シーン間クロスフェード秒数

# ── 音声設定 ────────────────────────────────────────────
NARR_DELAY = 0.5      # ナレーション開始前の余白（秒）
NARR_TAIL = 1.0       # ナレーション終了後の余白（秒）
MIN_CLIP_FLOOR = 5.0  # 音声ありシーンの最低クリップ尺（秒）
BGM_VOLUME = 0.12     # BGM音量（0〜1）
BGM_FADE_IN = 5       # BGMフェードイン秒数
BGM_FADE_OUT = 6      # BGMフェードアウト秒数

# ── イントロ・アウトロ設定 ──────────────────────────────────
LOGO_PATH = BASE_DIR / "LOGO_dark.PNG"  # 背景黒・クロップ済み版
FONT_PATH = Path("/System/Library/Fonts/Supplemental/Futura.ttc")
INTRO_DURATION = 5.0        # イントロ尺（秒）
OUTRO_MAIN_DURATION = 8.0   # 本編アウトロ尺（秒）
OUTRO_SHORTS_DURATION = 5.0 # Shortsアウトロ尺（秒）
OFFICIAL_SITE = "samurai-chronicles.com"

# ── Shorts v4 設定 ───────────────────────────────────────
SHORTS_CLIP_DURATION = 2.0   # 各シーンの表示秒数（v4: 2秒）
SHORTS_XFADE = 0.5           # クロスフェード秒数
SHORTS_BGM_VOL = 0.10        # BGM音量（Shorts用）
SHORTS_NARR_DELAY_MS = 200   # ナレーション開始前の余白（ms）
# シーン数はナレーション尺から動的計算（SHORTS_SCENE_COUNT は使用しない）
DIN_FONT = str(Path("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"))

# ── 本編 Teaser イントロ設定 ──────────────────────────────
TEASER_CLIP_DUR = 2.5     # テイザー1クリップ秒数
TEASER_XFADE    = 0.3     # 速めのクロスフェード（映画的テンポ感）
TEASER_MAX_CLIPS = 12     # テイザーに使う最大シーン数（ナレーション尺に合わせる）

# ── Ken Burns パラメータ ─────────────────────────────────
KB_ZOOM_FACTOR = 1.06   # zoom_in/out の最大倍率

# ── キャラクター表示名マッピング ──────────────────────────
CHAR_DISPLAY_NAMES = {
    "musashi":         "MIYAMOTO MUSASHI",
    "kojiro":          "SASAKI KOJIRO",
    "nobunaga":        "ODA NOBUNAGA",
    "hideyoshi":       "TOYOTOMI HIDEYOSHI",
    "ieyasu":          "TOKUGAWA IEYASU",
    "mitsuhide":       "AKECHI MITSUHIDE",
    "katsuie":         "SHIBATA KATSUIE",
    "yoshitsune":      "MINAMOTO YOSHITSUNE",
    "yoritomo":        "MINAMOTO YORITOMO",
    "kenshin":         "UESUGI KENSHIN",
    "shingen":         "TAKEDA SHINGEN",
    "masamune":        "DATE MASAMUNE",
    "saigo":           "SAIGO TAKAMORI",
    "yukimura":        "SANADA YUKIMURA",
    "mitsunari":       "ISHIDA MITSUNARI",
    "hattori_hanzo":   "HATTORI HANZO",
    "honda_tadakatsu": "HONDA TADAKATSU",
    "kuroda_kanbei":   "KURODA KANBEI",
    "tomoe_gozen":     "TOMOE GOZEN",
    "kiyomori":        "TAIRA KIYOMORI",
    "yagyu":           "YAGYU MUNENORI",
    "kusunoki":        "KUSUNOKI MASASHIGE",
    "naoe_kanetsugu":  "NAOE KANETSUGU",
    "ii_naomasa":      "II NAOMASA",
    "shimazu":         "SHIMAZU YOSHIHIRO",
    "mori_motonari":   "MORI MOTONARI",
    "chosokabe":       "CHOSOKABE MOTOCHIKA",
    "maeda_toshiie":   "MAEDA TOSHIIE",
    "tachibana_ginchiyo": "TACHIBANA GINCHIYO",
}


def _find_bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        print(f"エラー: {name} が見つかりません。brew install ffmpeg で導入してください。")
        sys.exit(1)
    return path


FFMPEG = _find_bin("ffmpeg")
FFPROBE = _find_bin("ffprobe")


def run_cmd(cmd: list, label: str = ""):
    if label:
        print(f"  [{label}] ", end="", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\nFFmpeg エラー:\n{result.stderr[-3000:]}")
        sys.exit(1)
    print("✓")


def probe_audio_duration(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    d = json.loads(r.stdout)
    for s in d["streams"]:
        if s.get("codec_type") == "audio":
            return float(s.get("duration", 0))
    return 0.0


def probe_video_duration(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    d = json.loads(r.stdout)
    for s in d["streams"]:
        if s.get("codec_type") == "video":
            return float(s.get("duration", 0))
    return 0.0


def make_intro_clip(dst: Path, landscape: bool = True):
    """ロゴ + タイトルのイントロクリップを生成する（音声なし）。"""
    w, h = (OUTPUT_W, OUTPUT_H) if landscape else (SHORTS_W, SHORTS_H)
    dur = INTRO_DURATION
    logo_w = 390 if landscape else 540  # 1.5倍サイズ
    font = str(FONT_PATH)

    logo_y = f"(H-h)/2-100" if landscape else f"(H-h)/2-220"
    title_y = f"h/2+{130 if landscape else 140}"
    title_size = 52 if landscape else 42

    run_cmd(
        [
            FFMPEG, "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x0a0a0a:size={w}x{h}:rate={FPS}:d={dur}",
            "-i", str(LOGO_PATH),
            "-filter_complex",
            (
                f"[1:v]scale={logo_w}:-1,format=rgba[logo];"
                f"[0:v][logo]overlay=(W-w)/2:{logo_y},"
                f"drawtext=fontfile={font}:text='SAMURAI  CHRONICLES'"
                f":fontsize={title_size}:fontcolor=white"
                f":x=(w-text_w)/2:y={title_y}"
                f":shadowx=2:shadowy=2:shadowcolor=black@0.5,"
                f"fade=t=in:st=0:d=1.2,"
                f"fade=t=out:st={dur-1.2:.1f}:d=1.2[vout]"
            ),
            "-map", "[vout]",
            "-t", str(dur),
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-pix_fmt", "yuv420p",
            str(dst),
        ],
        f"intro clip ({'main' if landscape else 'shorts'})",
    )


def make_outro_clip(dst: Path, landscape: bool = True, shorts: bool = False):
    """ロゴ + テキストのアウトロクリップを生成する（音声なし）。"""
    w, h = (OUTPUT_W, OUTPUT_H) if landscape else (SHORTS_W, SHORTS_H)
    dur = OUTRO_MAIN_DURATION if not shorts else OUTRO_SHORTS_DURATION
    logo_w = 330 if landscape else 540  # 1.5倍サイズ（intro と統一）
    font = str(FONT_PATH)

    logo_y = f"(H-h)/2-100" if landscape else f"(H-h)/2-220"
    line1_y = f"h/2+{130 if landscape else 140}"
    line2_y = f"h/2+{185 if landscape else 210}"
    line1_size = 38 if landscape else 36
    line2_size = 28 if landscape else 24

    if shorts:
        line1_text = "Full episode in description"
        line2_text = "v"
        line2_size = 52 if landscape else 46
    else:
        line1_text = OFFICIAL_SITE
        line2_text = "New episode every week  ·  Subscribe"

    gold = "0xd4a843"  # ゴールドカラー

    run_cmd(
        [
            FFMPEG, "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x0a0a0a:size={w}x{h}:rate={FPS}:d={dur}",
            "-i", str(LOGO_PATH),
            "-filter_complex",
            (
                f"[1:v]scale={logo_w}:-1,format=rgba[logo];"
                f"[0:v][logo]overlay=(W-w)/2:{logo_y},"
                f"drawtext=fontfile={font}:text='{line1_text}'"
                f":fontsize={line1_size}:fontcolor={gold}"
                f":x=(w-text_w)/2:y={line1_y}"
                f":shadowx=1:shadowy=1:shadowcolor=black@0.6"
                + (
                    f","
                    f"drawtext=fontfile={font}:text='{line2_text}'"
                    f":fontsize={line2_size}:fontcolor=white@0.85"
                    f":x=(w-text_w)/2:y={line2_y}"
                    if not shorts else ""
                ) +
                f","
                f"fade=t=in:st=0:d=1.5,"
                f"fade=t=out:st={dur-1.5:.1f}:d=1.5[vout]"
            ),
            "-map", "[vout]",
            "-t", str(dur),
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-pix_fmt", "yuv420p",
            str(dst),
        ],
        f"outro clip ({'shorts' if shorts else 'main'})",
    )


def concat_video_clips(clips: list, dst: Path):
    """複数の動画クリップを単純連結する（音声なし）。"""
    if len(clips) == 1:
        run_cmd([FFMPEG, "-y", "-i", str(clips[0]), "-c", "copy", str(dst)], "copy")
        return
    # concat filter
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    n = len(clips)
    filter_str = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vout]"
    run_cmd(
        [FFMPEG, "-y"] + inputs + [
            "-filter_complex", filter_str,
            "-map", "[vout]",
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            str(dst),
        ],
        f"concat {n} clips",
    )


def make_ken_burns(src: Path, dst: Path, duration: float, effect: str, landscape: bool = True,
                   overlay_vf: str = ""):
    """画像に Ken Burns エフェクトを適用して動画クリップを生成する。

    effect: "zoom_in" | "zoom_out" | "pan_right" | "pan_left" | "static"
    landscape: True=1920x1080, False=1080x1920 (Shorts)
    """
    w, h = (OUTPUT_W, OUTPUT_H) if landscape else (SHORTS_W, SHORTS_H)
    res = f"{w}:{h}"
    total_frames = int(duration * FPS)
    z = KB_ZOOM_FACTOR

    # 高解像度バッファ（ズーム・パン用に2倍スケール）
    buf_w, buf_h = w * 2, h * 2

    # 縦型（Shorts）の場合: 横長ソース画像を高さ基準でスケールして中央クロップ
    # 横型の場合: 指定解像度に直接スケール
    if not landscape:
        prescale = f"scale={buf_w}:{buf_h}:flags=lanczos:force_original_aspect_ratio=increase,crop={buf_w}:{buf_h}"
    else:
        prescale = f"scale={buf_w}:{buf_h}:flags=lanczos"

    if effect == "zoom_in":
        zoom_step = round((z - 1.0) / total_frames, 6)
        vf = (
            f"{prescale},"
            f"zoompan=z='min(1+{zoom_step}*on,{z})'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},"
            f"setsar=1,format=yuv420p"
        )
    elif effect == "zoom_out":
        zoom_step = round((z - 1.0) / total_frames, 6)
        vf = (
            f"{prescale},"
            f"zoompan=z='max({z}-{zoom_step}*on,1)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},"
            f"setsar=1,format=yuv420p"
        )
    elif effect == "pan_right":
        vf = (
            f"{prescale},"
            f"zoompan=z='{z}'"
            f":x='iw/2-(iw/zoom/2)+({buf_w}-{buf_w}/{z})/2*on/{total_frames}'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},"
            f"setsar=1,format=yuv420p"
        )
    elif effect == "pan_left":
        vf = (
            f"{prescale},"
            f"zoompan=z='{z}'"
            f":x='iw/2-(iw/zoom/2)+({buf_w}-{buf_w}/{z})/2*(1-on/{total_frames})'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},"
            f"setsar=1,format=yuv420p"
        )
    else:  # static
        vf = (
            f"{prescale},"
            f"zoompan=z='{z * 0.98}'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s={w}x{h}:fps={FPS},"
            f"setsar=1,format=yuv420p"
        )

    if overlay_vf:
        vf += "," + overlay_vf

    run_cmd(
        [
            FFMPEG, "-y",
            "-loop", "1", "-i", str(src),
            "-vf", vf,
            "-t", str(duration),
            "-r", str(FPS),
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-pix_fmt", "yuv420p",
            str(dst),
        ],
        f"KB {effect} S{src.stem[1:]} ({duration:.1f}s)",
    )


# ── Shorts v4 ヘルパー ──────────────────────────────────

def _safe_word(w: str) -> str:
    """FFmpeg drawtext で使えるよう特殊文字を除去"""
    return (w.replace("'", "")
             .replace('"', "")
             .replace(":", "")
             .replace("—", "-")
             .replace("\\", ""))


def _char_name_overlay(char_ref: str, visible_dur: float = 4.0) -> str:
    """キャラクター初登場シーン用: 名前を画面下部に表示するフィルター文字列を返す。
    visible_dur 秒間だけ表示し、フェードイン0.3s・フェードアウト0.5s。
    """
    name = CHAR_DISPLAY_NAMES.get(char_ref, char_ref.upper().replace("_", " "))
    fade_in = 0.3
    fade_out = 0.5
    fade_out_start = visible_dur - fade_out
    return (
        f"drawtext=fontfile={DIN_FONT}"
        f":text='{name}'"
        f":fontsize=62:fontcolor=white"
        f":borderw=4:bordercolor=black"
        f":x=(w-text_w)/2:y=h*0.84"
        f":alpha='if(lt(t,{fade_in}),t/{fade_in},"
        f"if(lt(t,{fade_out_start:.2f}),1,"
        f"max(0,({visible_dur:.2f}-t)/{fade_out})))'"
        f":enable='between(t,0,{visible_dur})'"
    )


def teaser_caption_for_clip(narration: str, audio_dur: float, clip_idx: int) -> str:
    """テイザー用: グローバルタイムライン位置を考慮した1ワード字幕フィルターを返す（横長）。"""
    import re as _re
    raw_words = [w for w in _re.split(r'\s+', narration.replace("—", "-")) if w]
    words = [_safe_word(w) for w in raw_words if _safe_word(w)]
    if not words:
        return ""

    word_dur = audio_dur / len(words)
    clip_start_g = clip_idx * (TEASER_CLIP_DUR - TEASER_XFADE)
    clip_end_g   = clip_start_g + TEASER_CLIP_DUR

    parts = []
    for i, word in enumerate(words):
        g_start = i * word_dur
        g_end   = g_start + word_dur
        if g_end <= clip_start_g or g_start >= clip_end_g:
            continue
        local_start = round(max(0.0, g_start - clip_start_g), 3)
        local_end   = round(min(TEASER_CLIP_DUR, g_end - clip_start_g), 3)
        parts.append(
            f"drawtext=fontfile={DIN_FONT}"
            f":text='{word}'"
            f":fontsize=110:fontcolor=white"
            f":borderw=7:bordercolor=black"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":enable='between(t,{local_start},{local_end})'"
        )
    return ",".join(parts)


def _auto_hook_lines(narration: str) -> list:
    """hook ナレーションの先頭2文を最大25文字に切り詰めて hook lines を自動生成するフォールバック。"""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', narration.strip())
    lines = []
    for s in sentences[:2]:
        # 25文字以上は切り詰め
        s = s.strip()
        if len(s) > 30:
            s = s[:28].rsplit(" ", 1)[0] + "..."
        lines.append(s.upper())
    return lines or [narration[:25].upper()]


def shorts_hook_text_filter(lines: list) -> str:
    """1クリップ目専用: DIN Condensed Bold 白・黒縁取り（最大3行）。
    lines: エピソードJSONの shorts_hook_lines フィールドから渡す。
    行数に応じてフォントサイズ・Y位置を自動調整。
    """
    # 行ごとのフォントサイズ・Y位置設定（最大3行）
    configs = [
        (160, "h*0.07"),
        (125, "h*0.22"),
        (68,  "h*0.37"),
    ]
    parts = []
    for i, text in enumerate(lines[:3]):
        fs, y = configs[i]
        safe = text.replace("'", "").replace('"', "").replace(":", "\\:")
        bw = 9 if i == 0 else (7 if i == 1 else 4)
        sh = 6 if i == 0 else (5 if i == 1 else 3)
        parts.append(
            f"drawtext=fontfile={DIN_FONT}:text='{safe}'"
            f":fontsize={fs}:fontcolor=white:borderw={bw}:bordercolor=black"
            f":shadowx={sh}:shadowy={sh}:shadowcolor=black@0.75"
            f":x=(w-text_w)/2:y={y}"
        )
    return ",".join(parts)


def shorts_caption_for_clip(narration: str, audio_dur: float, clip_idx: int) -> str:
    """グローバルタイムライン位置を考慮した1ワード字幕フィルターを返す。"""
    raw_words = [w for w in narration.replace("—", "-").split() if w]
    words = [_safe_word(w) for w in raw_words if _safe_word(w)]
    if not words:
        return ""

    word_dur = audio_dur / len(words)
    clip_start_g = clip_idx * (SHORTS_CLIP_DURATION - SHORTS_XFADE)
    clip_end_g   = clip_start_g + SHORTS_CLIP_DURATION

    parts = []
    for i, word in enumerate(words):
        g_start = i * word_dur
        g_end   = g_start + word_dur
        if g_end <= clip_start_g or g_start >= clip_end_g:
            continue
        local_start = round(max(0.0, g_start - clip_start_g), 3)
        local_end   = round(min(SHORTS_CLIP_DURATION, g_end - clip_start_g), 3)
        parts.append(
            f"drawtext=fontfile={DIN_FONT}"
            f":text='{word}'"
            f":fontsize=120:fontcolor=white"
            f":borderw=7:bordercolor=black"
            f":shadowx=4:shadowy=4:shadowcolor=black@0.75"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":enable='between(t,{local_start},{local_end})'"
        )
    return ",".join(parts)


def make_shorts_clip(img: Path, dst: Path, effect: str, overlay_vf: str = ""):
    """Shorts用クリップ生成（Ken Burns + テキストオーバーレイ）"""
    tf = int(SHORTS_CLIP_DURATION * FPS)
    bw, bh = SHORTS_W * 2, SHORTS_H * 2
    z = KB_ZOOM_FACTOR
    pre = (f"scale={bw}:{bh}:flags=lanczos"
           f":force_original_aspect_ratio=increase,crop={bw}:{bh}")

    if effect == "zoom_in":
        zs = round((z - 1.0) / tf, 6)
        kb = (f"zoompan=z='min(1+{zs}*on,{z})'"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={tf}:s={SHORTS_W}x{SHORTS_H}:fps={FPS}")
    elif effect == "zoom_out":
        zs = round((z - 1.0) / tf, 6)
        kb = (f"zoompan=z='max({z}-{zs}*on,1)'"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={tf}:s={SHORTS_W}x{SHORTS_H}:fps={FPS}")
    elif effect == "pan_right":
        kb = (f"zoompan=z='{z}'"
              f":x='iw/2-(iw/zoom/2)+({bw}-{bw}/{z})/2*on/{tf}'"
              f":y='ih/2-(ih/zoom/2)':d={tf}:s={SHORTS_W}x{SHORTS_H}:fps={FPS}")
    elif effect == "pan_left":
        kb = (f"zoompan=z='{z}'"
              f":x='iw/2-(iw/zoom/2)+({bw}-{bw}/{z})/2*(1-on/{tf})'"
              f":y='ih/2-(ih/zoom/2)':d={tf}:s={SHORTS_W}x{SHORTS_H}:fps={FPS}")
    else:
        kb = (f"zoompan=z='{z * 0.98}'"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={tf}:s={SHORTS_W}x{SHORTS_H}:fps={FPS}")

    vf = f"{pre},{kb},setsar=1,format=yuv420p"
    if overlay_vf:
        vf += "," + overlay_vf

    run_cmd([
        FFMPEG, "-y",
        "-loop", "1", "-i", str(img),
        "-vf", vf,
        "-t", str(SHORTS_CLIP_DURATION),
        "-r", str(FPS),
        "-c:v", "libx264", "-crf", "18", "-preset", "slow",
        "-pix_fmt", "yuv420p",
        str(dst),
    ], f"s-clip {img.stem}")


def shorts_crossfade_concat(clips: list, dst: Path):
    """Shorts用クロスフェード結合（SHORTS_XFADE使用）"""
    n = len(clips)
    cum, offsets = 0.0, []
    for i in range(n - 1):
        cum += SHORTS_CLIP_DURATION - SHORTS_XFADE
        offsets.append(round(cum, 3))
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    fc, prev = [], "0:v"
    for i in range(1, n):
        lbl = f"v{i}"
        fc.append(f"[{prev}][{i}:v]xfade=transition=fade"
                  f":duration={SHORTS_XFADE}:offset={offsets[i-1]}[{lbl}]")
        prev = lbl
    run_cmd([FFMPEG, "-y"] + inputs + [
        "-filter_complex", ";".join(fc),
        "-map", f"[{prev}]",
        "-c:v", "libx264", "-crf", "18", "-preset", "slow",
        str(dst),
    ], f"s-crossfade {n}clips")


# ── 本編 Teaser イントロ ──────────────────────────────────

def make_teaser_clip(scenes: list, img_dir: Path, tmp: Path, narr_dur: float,
                     teaser_narration: str = "") -> tuple:
    """
    クライマックス周辺のシーンで映画トレイラー風ダイジェストを生成する。
    戻り値: (teaser_video_path, teaser_dur)  ※映像のみ（音声なし）
    narr_dur: S00_teaser.wav の尺（クリップ数の計算に使用）
    teaser_narration: ナレーションテキスト（指定するとキネティック字幕を付与）
    """
    import math as _math

    # クリップ数 = ナレーション尺に合わせて動的計算
    n_clips = _math.ceil((narr_dur - TEASER_XFADE) / (TEASER_CLIP_DUR - TEASER_XFADE))
    n_clips = min(max(n_clips, 3), TEASER_MAX_CLIPS)

    # 優先度順に劇的なシーンを選択（climax → falling_action → rising_action → setup）
    teaser_scene_ids = []
    for ptype in ["climax", "falling_action", "rising_action", "setup", "hook"]:
        for s in scenes:
            if len(teaser_scene_ids) >= n_clips:
                break
            if s["type"] == ptype and s["scene_id"] not in teaser_scene_ids:
                teaser_scene_ids.append(s["scene_id"])
        if len(teaser_scene_ids) >= n_clips:
            break

    # 不足する場合は先頭シーンで補完
    if len(teaser_scene_ids) < n_clips:
        for s in scenes:
            if s["scene_id"] not in teaser_scene_ids:
                teaser_scene_ids.append(s["scene_id"])
            if len(teaser_scene_ids) >= n_clips:
                break

    # クリップ生成（横長 1920x1080）
    t_clips = []
    for i, sid in enumerate(teaser_scene_ids[:n_clips]):
        img = img_dir / f"S{sid:02d}.png"
        if not img.exists():
            continue
        scene = next((s for s in scenes if s["scene_id"] == sid), None)
        effect = scene.get("ken_burns", "zoom_in") if scene else "zoom_in"
        dst_clip = tmp / f"teaser_{i:02d}.mp4"
        caption_vf = teaser_caption_for_clip(teaser_narration, narr_dur, i) if teaser_narration else ""
        make_ken_burns(img, dst_clip, TEASER_CLIP_DUR, effect, landscape=True, overlay_vf=caption_vf)
        t_clips.append(dst_clip)

    if not t_clips:
        return None, 0.0

    # クロスフェード結合（TEASER_XFADE 使用）
    if len(t_clips) == 1:
        teaser_video = t_clips[0]
    else:
        teaser_video = tmp / "teaser_video.mp4"
        n = len(t_clips)
        cum, offsets = 0.0, []
        for i in range(n - 1):
            cum += TEASER_CLIP_DUR - TEASER_XFADE
            offsets.append(round(cum, 3))
        inputs_f = []
        for c in t_clips:
            inputs_f += ["-i", str(c)]
        fc, prev = [], "0:v"
        for i in range(1, n):
            lbl = f"tv{i}"
            fc.append(f"[{prev}][{i}:v]xfade=transition=fade"
                      f":duration={TEASER_XFADE}:offset={offsets[i-1]}[{lbl}]")
            prev = lbl
        run_cmd([FFMPEG, "-y"] + inputs_f + [
            "-filter_complex", ";".join(fc),
            "-map", f"[{prev}]",
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            str(teaser_video),
        ], f"teaser xfade {n}clips")

    teaser_dur = (TEASER_CLIP_DUR - TEASER_XFADE) * (len(t_clips) - 1) + TEASER_CLIP_DUR
    print(f"  テイザー: {len(t_clips)}シーン × {TEASER_CLIP_DUR}s = {teaser_dur:.1f}s")
    return teaser_video, teaser_dur


# ── 既存ヘルパー ─────────────────────────────────────────

def crossfade_concat_n(clips: list, durations: list, dst: Path):
    """N個のクリップをクロスフェードで結合する。"""
    d = CROSSFADE_DURATION
    n = len(clips)

    # クロスフェードのオフセット計算
    offsets = []
    cumulative = 0.0
    for i in range(n - 1):
        cumulative += durations[i] - d
        offsets.append(round(cumulative, 3))

    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]

    if n == 1:
        run_cmd(
            [FFMPEG, "-y", "-i", str(clips[0]), "-c", "copy", str(dst)],
            "copy (1 clip)",
        )
        return

    # フィルターチェーン構築
    fc_parts = []
    prev = "0:v"
    for i in range(1, n):
        out_label = f"v{i}"
        fc_parts.append(
            f"[{prev}][{i}:v]xfade=transition=fade:duration={d}:offset={offsets[i-1]}[{out_label}]"
        )
        prev = out_label

    run_cmd(
        [FFMPEG, "-y"] + inputs + [
            "-filter_complex", ";".join(fc_parts),
            "-map", f"[{prev}]",
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            str(dst),
        ],
        f"crossfade concat ({n} clips)",
    )


def build_audio_track(scenes: list, audio_dir: Path, total_video_dur: float,
                      bgm_path: Path, dst: Path, scene_offsets: list,
                      intro_dur: float = 0.0, teaser_wav: Path = None):
    """全シーンのナレーションを配置し BGM とミックスしたオーディオトラックを生成する。

    teaser_wav: テイザーナレーション（S00_teaser.wav）を指定すると offset=NARR_DELAY で配置。
                scene_offsets は teaser_dur を含む intro_dur で既にオフセット済みであること。
    """
    narr_filters = []
    narr_inputs  = []
    all_labels   = []   # amix に渡すラベルをここで管理

    # ── テイザーナレーション（offset ≈ 0） ─────────────
    if teaser_wav and teaser_wav.exists():
        delay_ms = int(NARR_DELAY * 1000)
        narr_inputs.append(teaser_wav)
        narr_filters.append(f"[0:a]adelay={delay_ms}:all=1[nt]")
        all_labels.append("[nt]")

    # ── シーンナレーション ──────────────────────────────
    for i, scene in enumerate(scenes):
        scene_id = scene["scene_id"]
        wav = audio_dir / f"S{scene_id:02d}.wav"
        if not wav.exists():
            continue
        offset_ms = int((scene_offsets[i] + intro_dur) * 1000 + NARR_DELAY * 1000)
        idx = len(narr_inputs)  # 0-based（音声のみのコマンド）
        narr_inputs.append(wav)
        lbl = f"n{i}"
        narr_filters.append(f"[{idx}:a]adelay={offset_ms}:all=1[{lbl}]")
        all_labels.append(f"[{lbl}]")

    n_narr = len(narr_inputs)
    if n_narr == 0:
        # ナレーションなし: BGMのみ
        bgm_fadeout_start = max(0.0, total_video_dur - BGM_FADE_OUT)
        run_cmd(
            [
                FFMPEG, "-y",
                "-i", str(bgm_path),
                "-filter_complex",
                (
                    f"[0:a]aloop=loop=-1:size=2000000000,"
                    f"atrim=duration={total_video_dur},"
                    f"volume={BGM_VOLUME},"
                    f"afade=t=in:st=0:d={BGM_FADE_IN},"
                    f"afade=t=out:st={bgm_fadeout_start:.1f}:d={BGM_FADE_OUT}[aout]"
                ),
                "-map", "[aout]",
                "-c:a", "aac", "-b:a", "192k",
                str(dst),
            ],
            "BGM only",
        )
        return

    # 全ナレーションをミックス（all_labels を使用）
    n_mix = len(all_labels)
    narr_filters.append(
        f"{''.join(all_labels)}amix=inputs={n_mix}:duration=longest:normalize=0[narr_mix]"
    )
    # ナレーションのパッド
    narr_filters.append(
        f"[narr_mix]apad=whole_dur={total_video_dur}[narr_padded]"
    )

    bgm_fadeout_start = max(0.0, total_video_dur - BGM_FADE_OUT)
    # BGMフィルター（narr_inputs の直後の入力）
    bgm_idx = len(narr_inputs)
    narr_filters.append(
        f"[{bgm_idx}:a]aloop=loop=-1:size=2000000000,"
        f"atrim=duration={total_video_dur},"
        f"volume={BGM_VOLUME},"
        f"afade=t=in:st=0:d={BGM_FADE_IN},"
        f"afade=t=out:st={bgm_fadeout_start:.1f}:d={BGM_FADE_OUT}[bgm_loop]"
    )
    narr_filters.append(
        "[narr_padded][bgm_loop]amix=inputs=2:duration=first:normalize=0[aout]"
    )

    inputs_flat = []
    for wav in narr_inputs:
        inputs_flat += ["-i", str(wav)]
    inputs_flat += ["-i", str(bgm_path)]

    run_cmd(
        [
            FFMPEG, "-y",
        ] + inputs_flat + [
            "-filter_complex", ";".join(narr_filters),
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            str(dst),
        ],
        "mix narration + BGM",
    )


def gen_video(episode_id: str, out_dir: Path = None, shorts_only: bool = False):
    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    img_dir = DRIVE_BASE / episode_id / "images"
    img_dir_shorts = DRIVE_BASE / episode_id / "images_shorts"
    audio_dir = DRIVE_BASE / episode_id / "audio"
    bgm_path = audio_dir / f"{episode_id}-BGM.mp3"

    if out_dir is None:
        out_dir = DRIVE_BASE / episode_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes = ep["scenes"]
    shorts_scene_id = ep.get("shorts_highlight_scene", 1)

    # ── 各シーンの尺を決定 ─────────────────────────────
    print(f"\n{'━'*60}")
    print(f"  {episode_id} — 動画生成開始")
    print(f"  シーン数: {len(scenes)}")
    print(f"{'━'*60}\n")

    print("--- シーン尺解析 ---")
    scene_durations = []
    for scene in scenes:
        sid = scene["scene_id"]
        min_dur = float(scene.get("duration_seconds", 10))
        wav = audio_dir / f"S{sid:02d}.wav"
        if wav.exists():
            narr_dur = probe_audio_duration(wav)
            clip_dur = max(MIN_CLIP_FLOOR, narr_dur + NARR_DELAY + NARR_TAIL)
        else:
            clip_dur = min_dur
            narr_dur = 0.0
        scene_durations.append(round(clip_dur, 2))
        print(f"  S{sid:02d}: ナレーション {narr_dur:.1f}s → クリップ {clip_dur:.1f}s")

    # クロスフェードを考慮したシーン開始オフセット
    scene_offsets = [0.0]
    for i in range(1, len(scenes)):
        scene_offsets.append(
            scene_offsets[-1] + scene_durations[i - 1] - CROSSFADE_DURATION
        )

    total_dur = scene_offsets[-1] + scene_durations[-1]
    print(f"\n  合計尺: {total_dur:.1f}s ({total_dur/60:.1f}分)")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)

        # ── Shorts v4 生成 ────────────────────────────────
        import math as _math
        shorts_narration = ep.get("shorts_narration", "")
        shorts_wav = audio_dir / "S00_shorts.wav"

        if not shorts_narration:
            print("\n  ⚠️  shorts_narration フィールドなし — Shorts 生成をスキップ")
        elif not shorts_wav.exists():
            print(f"\n  ⚠️  {shorts_wav.name} が見つかりません")
            print(f"      先に: python3 sc_tts_gen.py --episode {episode_id} --shorts")
        else:
            narr_dur = probe_audio_duration(shorts_wav)
            # ナレーション尺からシーン数を動的計算
            scene_count = _math.ceil((narr_dur - SHORTS_XFADE) / (SHORTS_CLIP_DURATION - SHORTS_XFADE))
            scene_count = max(scene_count, 5)

            # シーン選択（highlight必須、priority順）
            selected_ids = {shorts_scene_id} if shorts_scene_id else set()
            for ptype in ["hook", "climax", "teaser", "insight",
                          "falling_action", "rising_action", "setup"]:
                for s in scenes:
                    if len(selected_ids) >= scene_count:
                        break
                    if s["type"] == ptype and s["scene_id"] not in selected_ids:
                        selected_ids.add(s["scene_id"])
                if len(selected_ids) >= scene_count:
                    break
            selected_s = sorted(
                [s for s in scenes if s["scene_id"] in selected_ids],
                key=lambda s: s["scene_id"],
            )
            print(f"\n--- Shorts v4 クリップ生成 ({len(selected_s)}シーン×{SHORTS_CLIP_DURATION}s) ---")
            print(f"  ナレーション尺: {narr_dur:.1f}s  使用シーン: {[s['scene_id'] for s in selected_s]}")

            # エピソードごとの hook テキスト（shorts_hook_lines 優先、なければ hook シーンから自動生成）
            hook_lines = ep.get("shorts_hook_lines")
            if not hook_lines:
                hook_scene = next((s for s in scenes if s.get("type") == "hook"), None)
                if hook_scene:
                    hook_lines = _auto_hook_lines(hook_scene["narration"])
                else:
                    hook_lines = ["SAMURAI CHRONICLES"]

            s_clips = []
            clip_idx = 0
            for scene in selected_s:
                sid    = scene["scene_id"]
                effect = scene.get("ken_burns", "zoom_in")
                img    = img_dir_shorts / f"S{sid:02d}.png"
                if not img.exists():
                    img = img_dir / f"S{sid:02d}.png"
                if not img.exists():
                    continue
                if clip_idx == 0:
                    overlay = shorts_hook_text_filter(hook_lines)
                else:
                    overlay = shorts_caption_for_clip(shorts_narration, narr_dur, clip_idx)
                out_clip = tmp / f"s_clip_{sid:02d}.mp4"
                make_shorts_clip(img, out_clip, effect, overlay)
                s_clips.append(out_clip)
                clip_idx += 1

            if s_clips:
                s_main = tmp / "s_main.mp4"
                shorts_crossfade_concat(s_clips, s_main)

                s_outro = tmp / "s_outro.mp4"
                make_outro_clip(s_outro, landscape=False, shorts=True)

                s_video = tmp / "s_video.mp4"
                concat_video_clips([s_main, s_outro], s_video)

                n_clips = len(s_clips)
                s_main_dur = (SHORTS_CLIP_DURATION - SHORTS_XFADE) * (n_clips - 1) + SHORTS_CLIP_DURATION
                s_total_dur = s_main_dur + OUTRO_SHORTS_DURATION
                fade_start = max(0.0, s_total_dur - 5)

                shorts_audio = tmp / "s_audio.aac"
                run_cmd([
                    FFMPEG, "-y",
                    "-i", str(shorts_wav),
                    "-i", str(bgm_path),
                    "-filter_complex",
                    (
                        f"[0:a]adelay={SHORTS_NARR_DELAY_MS}:all=1"
                        f",apad=whole_dur={s_total_dur}[narr];"
                        f"[1:a]aloop=loop=-1:size=2000000000"
                        f",atrim=duration={s_total_dur}"
                        f",volume={SHORTS_BGM_VOL}"
                        f",afade=t=in:st=0:d=3"
                        f",afade=t=out:st={fade_start:.1f}:d=5[bgm];"
                        f"[narr][bgm]amix=inputs=2:duration=first:normalize=0[aout]"
                    ),
                    "-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
                    str(shorts_audio),
                ], "s-audio mix")

                shorts_output = out_dir / f"{episode_id}_shorts.mp4"
                run_cmd([
                    FFMPEG, "-y",
                    "-i", str(s_video), "-i", str(shorts_audio),
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "copy", "-shortest",
                    str(shorts_output),
                ], f"Shorts 合成 → {shorts_output.name}")
                print(f"  ✓ Shorts: {shorts_output}")

        if shorts_only:
            print("\n  --shorts オプション: 本編生成をスキップします")
            return

        # ── Step 1: テイザーイントロ生成 ──────────────────
        teaser_narration = ep.get("teaser_narration", "")
        teaser_wav       = audio_dir / "S00_teaser.wav"
        teaser_video_path = None
        teaser_dur        = 0.0

        if teaser_narration and teaser_wav.exists():
            print(f"\n--- Step 1: テイザーイントロ生成 ---")
            teaser_narr_dur = probe_audio_duration(teaser_wav)
            teaser_video_path, teaser_dur = make_teaser_clip(
                scenes, img_dir, tmp, teaser_narr_dur, teaser_narration=teaser_narration
            )
        else:
            if teaser_narration and not teaser_wav.exists():
                print(f"\n  ⚠️  S00_teaser.wav が見つかりません")
                print(f"      先に: python3 sc_tts_gen.py --episode {episode_id} --teaser")
            print(f"\n--- Step 1: イントロ / アウトロ生成 ---")

        # ── Step 2: チャンネルイントロ・アウトロ生成 ─────────
        print(f"\n--- Step 2: チャンネルイントロ / アウトロ生成 ---")
        intro_clip = tmp / "intro.mp4"
        outro_clip = tmp / "outro.mp4"
        make_intro_clip(intro_clip, landscape=True)
        make_outro_clip(outro_clip, landscape=True, shorts=False)

        # ── Step 3: 各シーン Ken Burns クリップ生成 ────────
        print(f"\n--- Step 3: Ken Burns クリップ生成 ({len(scenes)}シーン) ---")
        clip_paths = []
        seen_chars: set = set()   # キャラクター初登場トラッキング
        for i, scene in enumerate(scenes):
            sid = scene["scene_id"]
            img = img_dir / f"S{sid:02d}.png"
            effect = scene.get("ken_burns", "zoom_in")
            dur = scene_durations[i]
            out_clip = tmp / f"clip_{sid:02d}.mp4"

            if not img.exists():
                print(f"  ⚠️  S{sid:02d}: 画像なし ({img}) — スキップ")
                continue

            # キャラクター初登場なら名前オーバーレイを付与
            char_ref = scene.get("character_ref")
            overlay_vf = ""
            if char_ref and char_ref not in seen_chars:
                seen_chars.add(char_ref)
                overlay_vf = _char_name_overlay(char_ref, visible_dur=4.0)

            make_ken_burns(img, out_clip, dur, effect, landscape=True, overlay_vf=overlay_vf)
            clip_paths.append((out_clip, dur))

        if not clip_paths:
            print("❌ 生成できるクリップがありません")
            sys.exit(1)

        # ── Step 4: シーンをクロスフェード結合 ─────────────
        print(f"\n--- Step 4: クロスフェード結合 ({len(clip_paths)}クリップ) ---")
        clips = [p for p, _ in clip_paths]
        durs  = [d for _, d in clip_paths]
        scenes_video = tmp / "scenes_video.mp4"
        crossfade_concat_n(clips, durs, scenes_video)

        # ── Step 5: 映像全結合 ─────────────────────────────
        # テイザーがあれば先頭に付与
        print(f"\n--- Step 5: 映像全結合 ---")
        full_video = tmp / "full_video.mp4"
        video_parts = []
        if teaser_video_path:
            video_parts.append(teaser_video_path)
        video_parts += [intro_clip, scenes_video, outro_clip]
        concat_video_clips(video_parts, full_video)

        # ── Step 6: 音声ミックス ──────────────────────────
        print(f"\n--- Step 6: 音声ミックス ---")
        # テイザー分だけイントロオフセットを加算
        effective_intro_dur = teaser_dur + INTRO_DURATION
        total_full_dur = teaser_dur + INTRO_DURATION + total_dur + OUTRO_MAIN_DURATION
        audio_only = tmp / "audio_only.aac"
        build_audio_track(
            scenes, audio_dir, total_full_dur, bgm_path,
            audio_only, scene_offsets,
            intro_dur=effective_intro_dur,
            teaser_wav=teaser_wav if (teaser_video_path and teaser_wav.exists()) else None,
        )

        # ── Step 7: 最終合成 ────────────────────────────
        print(f"\n--- Step 7: 最終合成 ---")
        output_file = out_dir / f"Samurai Chronicles {episode_id}.mp4"
        run_cmd(
            [
                FFMPEG, "-y",
                "-i", str(full_video),
                "-i", str(audio_only),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "copy",
                "-shortest",
                str(output_file),
            ],
            f"最終合成 → {output_file.name}",
        )

    print(f"\n{'━'*60}")
    print(f"  ✓ 完成: {output_file}")
    if teaser_dur > 0:
        print(f"  構成: テイザー {teaser_dur:.0f}s + イントロ {INTRO_DURATION:.0f}s"
              f" + 本編 {total_dur:.0f}s + アウトロ {OUTRO_MAIN_DURATION:.0f}s")
    print(f"  合計尺: {total_full_dur:.1f}s ({total_full_dur/60:.1f}分)")

    # ── YouTube チャプタータイムスタンプ生成 + JSON自動更新 ──
    def _fmt_ts(sec: float) -> str:
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m}:{s:02d}"

    def _chapter_label(scene: dict) -> str:
        """シーンナレーションの最初の数語からチャプター名を生成"""
        import re as _re
        narr = scene.get("narration", "")
        words = _re.split(r'\s+', narr.strip())[:6]
        label = " ".join(words)
        if len(label) > 32:
            label = label[:30].rsplit(" ", 1)[0] + "..."
        return label

    chapter_lines = ["0:00 Introduction"]
    for i, scene in enumerate(scenes):
        t = teaser_dur + INTRO_DURATION + scene_offsets[i]
        chapter_lines.append(f"{_fmt_ts(t)} {_chapter_label(scene)}")
    chapter_block = "\n".join(chapter_lines)

    print(f"\n{'━'*60}")
    print(f"  📌 YouTube チャプター（概要欄に自動反映）:")
    print()
    for line in chapter_lines:
        print(f"  {line}")
    print()

    # ── episode JSON の youtube_description にチャプターを挿入 ──
    desc = ep.get("youtube_description", "")
    # 既存チャプターブロックを除去（再生成対応）
    import re as _re2
    desc = _re2.sub(r'⏱️ Chapters:\n(?:\d+:\d{2} .+\n?)+\n?', '', desc)
    # 🎌 Subscribe 行の直前に挿入
    insert_marker = "🎌 Subscribe"
    if insert_marker in desc:
        desc = desc.replace(insert_marker, f"⏱️ Chapters:\n{chapter_block}\n\n{insert_marker}", 1)
    else:
        desc = desc.rstrip() + f"\n\n⏱️ Chapters:\n{chapter_block}"
    ep["youtube_description"] = desc

    # JSON を上書き保存
    with open(ep_json, "w", encoding="utf-8") as _f:
        json.dump(ep, _f, ensure_ascii=False, indent=2)
    print(f"  ✓ {ep_json.name} の youtube_description を更新しました")
    print(f"{'━'*60}\n")

    return output_file


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles 動画生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    parser.add_argument("--output", default=None, help="出力ディレクトリ（デフォルト: output/{episode_id}/）")
    parser.add_argument("--shorts", action="store_true", help="Shortsクリップのみ生成")
    args = parser.parse_args()

    out_dir = Path(args.output).expanduser().resolve() if args.output else None
    gen_video(args.episode, out_dir=out_dir, shorts_only=args.shorts)


if __name__ == "__main__":
    cli()
