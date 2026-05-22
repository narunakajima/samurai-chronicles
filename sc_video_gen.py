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

# ── Shorts マルチシーン設定 ───────────────────────────────
SHORTS_CLIP_DURATION = 5.0   # 各シーンの表示秒数
SHORTS_SCENE_COUNT = 8        # 使用シーン数（均等分散）

# ── Ken Burns パラメータ ─────────────────────────────────
KB_ZOOM_FACTOR = 1.06   # zoom_in/out の最大倍率


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


def make_ken_burns(src: Path, dst: Path, duration: float, effect: str, landscape: bool = True):
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
                      intro_dur: float = 0.0):
    """全シーンのナレーションを配置し BGM とミックスしたオーディオトラックを生成する。"""

    # ナレーションをディレイ付きで並べるフィルター
    narr_filters = []
    narr_inputs = []
    for i, scene in enumerate(scenes):
        scene_id = scene["scene_id"]
        wav = audio_dir / f"S{scene_id:02d}.wav"
        if not wav.exists():
            continue
        offset_ms = int((scene_offsets[i] + intro_dur) * 1000 + NARR_DELAY * 1000)
        idx = len(narr_inputs)  # 0-based（音声のみのコマンド）
        narr_inputs.append(wav)
        narr_filters.append(f"[{idx}:a]adelay={offset_ms}:all=1[n{i}]")

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

    # 全ナレーションをミックス
    mix_labels = [f"[n{i}]" for i in range(n_narr)]
    narr_filters.append(
        f"{''.join(mix_labels)}amix=inputs={n_narr}:duration=longest:normalize=0[narr_mix]"
    )
    # ナレーションのパッド
    narr_filters.append(
        f"[narr_mix]apad=whole_dur={total_video_dur}[narr_padded]"
    )

    bgm_fadeout_start = max(0.0, total_video_dur - BGM_FADE_OUT)
    # BGMフィルター（narr_inputs の直後の入力）
    bgm_idx = n_narr
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
        min_dur = float(scene.get("duration_seconds", 20))
        wav = audio_dir / f"S{sid:02d}.wav"
        if wav.exists():
            narr_dur = probe_audio_duration(wav)
            clip_dur = max(min_dur, narr_dur + NARR_DELAY + NARR_TAIL)
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

        # ── Shorts 用クリップ（イントロ + マルチシーン + アウトロ）──
        n_s = min(SHORTS_SCENE_COUNT, len(scenes))
        s_indices = [round(i * (len(scenes) - 1) / (n_s - 1)) for i in range(n_s)]
        selected = [scenes[i] for i in s_indices]
        print(f"\n--- Shorts クリップ生成 (イントロ + {n_s}シーン×{SHORTS_CLIP_DURATION}s + アウトロ) ---")
        print(f"  使用シーン: {[s['scene_id'] for s in selected]}")

        s_clips = []
        for scene in selected:
            sid = scene["scene_id"]
            # Shorts専用縦長画像を優先、なければ通常画像（クロップ）
            img = img_dir_shorts / f"S{sid:02d}.png"
            if not img.exists():
                img = img_dir / f"S{sid:02d}.png"
            if not img.exists():
                continue
            effect = scene.get("ken_burns", "zoom_in")
            out_clip = tmp / f"s_clip_{sid:02d}.mp4"
            make_ken_burns(img, out_clip, SHORTS_CLIP_DURATION, effect, landscape=False)
            s_clips.append(out_clip)

        if s_clips:
            s_intro = tmp / "s_intro.mp4"
            make_intro_clip(s_intro, landscape=False)

            s_main = tmp / "s_main.mp4"
            s_durs = [SHORTS_CLIP_DURATION] * len(s_clips)
            crossfade_concat_n(s_clips, s_durs, s_main)
            s_main_dur = sum(d - CROSSFADE_DURATION for d in s_durs[:-1]) + s_durs[-1]

            s_outro = tmp / "s_outro.mp4"
            make_outro_clip(s_outro, landscape=False, shorts=True)

            s_video = tmp / "s_video.mp4"
            concat_video_clips([s_intro, s_main, s_outro], s_video)

            s_total_dur = INTRO_DURATION + s_main_dur + OUTRO_SHORTS_DURATION
            shorts_audio = tmp / "s_audio.aac"
            # ハイライトシーンのナレーション + BGM
            highlight = next((s for s in scenes if s["scene_id"] == shorts_scene_id), None)
            narr_scenes = [highlight] if highlight else []
            build_audio_track(narr_scenes, audio_dir, s_total_dur, bgm_path,
                              shorts_audio, [0.0], intro_dur=INTRO_DURATION)

            shorts_output = out_dir / f"{episode_id}_shorts.mp4"
            run_cmd(
                [
                    FFMPEG, "-y",
                    "-i", str(s_video),
                    "-i", str(shorts_audio),
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "copy",
                    "-shortest",
                    str(shorts_output),
                ],
                f"Shorts 合成 → {shorts_output.name}",
            )
            print(f"  ✓ Shorts: {shorts_output}")

        if shorts_only:
            print("\n  --shorts オプション: 本編生成をスキップします")
            return

        # ── Step 1: イントロ・アウトロクリップ生成 ────────
        print(f"\n--- Step 1: イントロ / アウトロ生成 ---")
        intro_clip = tmp / "intro.mp4"
        outro_clip = tmp / "outro.mp4"
        make_intro_clip(intro_clip, landscape=True)
        make_outro_clip(outro_clip, landscape=True, shorts=False)

        # ── Step 2: 各シーン Ken Burns クリップ生成 ────────
        print(f"\n--- Step 2: Ken Burns クリップ生成 ({len(scenes)}シーン) ---")
        clip_paths = []
        for i, scene in enumerate(scenes):
            sid = scene["scene_id"]
            img = img_dir / f"S{sid:02d}.png"
            effect = scene.get("ken_burns", "zoom_in")
            dur = scene_durations[i]
            out_clip = tmp / f"clip_{sid:02d}.mp4"

            if not img.exists():
                print(f"  ⚠️  S{sid:02d}: 画像なし ({img}) — スキップ")
                continue
            make_ken_burns(img, out_clip, dur, effect, landscape=True)
            clip_paths.append((out_clip, dur))

        if not clip_paths:
            print("❌ 生成できるクリップがありません")
            sys.exit(1)

        # ── Step 3: シーンをクロスフェード結合 ─────────────
        print(f"\n--- Step 3: クロスフェード結合 ({len(clip_paths)}クリップ) ---")
        clips = [p for p, _ in clip_paths]
        durs = [d for _, d in clip_paths]
        scenes_video = tmp / "scenes_video.mp4"
        crossfade_concat_n(clips, durs, scenes_video)

        # ── Step 4: イントロ + シーン + アウトロ結合 ─────────
        print(f"\n--- Step 4: イントロ + 本編 + アウトロ結合 ---")
        full_video = tmp / "full_video.mp4"
        concat_video_clips([intro_clip, scenes_video, outro_clip], full_video)

        # ── Step 5: 音声ミックス（イントロ分オフセット）──────
        print(f"\n--- Step 5: 音声ミックス ---")
        total_full_dur = INTRO_DURATION + total_dur + OUTRO_MAIN_DURATION
        audio_only = tmp / "audio_only.aac"
        build_audio_track(
            scenes, audio_dir, total_full_dur, bgm_path,
            audio_only, scene_offsets, intro_dur=INTRO_DURATION
        )

        # ── Step 6: 最終合成 ────────────────────────────
        print(f"\n--- Step 6: 最終合成 ---")
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
    print(f"  尺: {total_full_dur:.1f}s ({total_full_dur/60:.1f}分)")
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
