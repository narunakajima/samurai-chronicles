"""
sc_subtitle_gen.py — Samurai Chronicles 字幕(SRT)生成スクリプト

使い方:
  python3 sc_subtitle_gen.py --episode ep001
  → Google Drive の ep001/output/ep001.srt を生成

タイムスタンプの計算:
  イントロ(5s) + シーンオフセット + ナレーション遅延(0.5s) = 字幕開始
  字幕終了 = 開始 + ナレーション音声長
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)

INTRO_DURATION = 5.0
NARR_DELAY = 0.5
NARR_TAIL = 1.0
CROSSFADE_DURATION = 0.8


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    d = json.loads(r.stdout)
    for s in d.get("streams", []):
        if s.get("codec_type") == "audio":
            return float(s.get("duration", 0))
    return 0.0


def seconds_to_srt(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run(episode_id: str):
    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    audio_dir = DRIVE_BASE / episode_id / "audio"
    out_dir = DRIVE_BASE / episode_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes = ep["scenes"]

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — 字幕生成")
    print(f"{'━'*60}\n")

    # シーン尺とオフセットを計算
    scene_durations = []
    narr_durations = []
    for scene in scenes:
        sid = scene["scene_id"]
        min_dur = float(scene.get("duration_seconds", 20))
        wav = audio_dir / f"S{sid:02d}.wav"
        if wav.exists():
            narr_dur = probe_duration(wav)
        else:
            narr_dur = 0.0
        clip_dur = max(min_dur, narr_dur + NARR_DELAY + NARR_TAIL)
        scene_durations.append(round(clip_dur, 3))
        narr_durations.append(narr_dur)

    scene_offsets = [0.0]
    for i in range(1, len(scenes)):
        scene_offsets.append(
            scene_offsets[-1] + scene_durations[i - 1] - CROSSFADE_DURATION
        )

    # SRT生成
    srt_lines = []
    idx = 1
    for i, scene in enumerate(scenes):
        narr_dur = narr_durations[i]
        if narr_dur <= 0:
            continue

        start = INTRO_DURATION + scene_offsets[i] + NARR_DELAY
        end = start + narr_dur

        text = scene["narration"].strip()

        srt_lines.append(str(idx))
        srt_lines.append(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}")
        srt_lines.append(text)
        srt_lines.append("")

        print(f"  S{scene['scene_id']:02d}: {seconds_to_srt(start)} → {seconds_to_srt(end)}")
        idx += 1

    srt_content = "\n".join(srt_lines)
    out_path = out_dir / f"{episode_id}.srt"
    out_path.write_text(srt_content, encoding="utf-8")

    print(f"\n{'━'*60}")
    print(f"  ✓ 完成: {out_path}")
    print(f"  エントリ数: {idx - 1}")
    print(f"{'━'*60}\n")
    return out_path


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles 字幕生成")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    args = parser.parse_args()
    run(args.episode)


if __name__ == "__main__":
    cli()
