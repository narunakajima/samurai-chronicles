"""
sc_subtitle_gen.py — Samurai Chronicles 字幕(SRT)生成スクリプト

使い方:
  python3 sc_subtitle_gen.py --episode ep001
  → Google Drive の ep001/output/ep001.srt を生成

タイムスタンプの計算:
  イントロ(5s) + シーンオフセット + ナレーション遅延(0.5s) = 字幕開始
  ナレーションを文単位に分割し、語数比率でタイムスタンプを按分する。
"""

import argparse
import json
import re
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

# テイザーイントロ設定（sc_video_gen.py と同値）
TEASER_CLIP_DUR = 2.5
TEASER_XFADE = 0.3
TEASER_MAX_CLIPS = 5


def split_sentences(text: str) -> list:
    """ナレーションを文単位に分割する。"""
    # ピリオド・感嘆符・疑問符の後ろで分割
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_sentence(text: str, max_chars: int = 42) -> list:
    """文を「最大2行・1行あたりmax_chars文字」のチャンクリストに分割する。
    1チャンクが2行を超える場合は次のチャンクへ繰り越す。"""
    words = text.split()
    chunks = []
    line1, line2 = [], []

    for word in words:
        if not line1:
            line1.append(word)
        elif len(" ".join(line1 + [word])) <= max_chars:
            line1.append(word)
        elif not line2:
            line2.append(word)
        elif len(" ".join(line2 + [word])) <= max_chars:
            line2.append(word)
        else:
            # 2行が埋まったのでチャンク確定
            chunk = " ".join(line1)
            if line2:
                chunk += "\n" + " ".join(line2)
            chunks.append(chunk)
            line1 = [word]
            line2 = []

    if line1:
        chunk = " ".join(line1)
        if line2:
            chunk += "\n" + " ".join(line2)
        chunks.append(chunk)

    return chunks if chunks else [text]


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

    # テイザー尺を計算（S00_teaser.wav がある場合）
    import math as _math
    teaser_wav = audio_dir / "S00_teaser.wav"
    teaser_dur = 0.0
    if teaser_wav.exists():
        teaser_narr_dur = probe_duration(teaser_wav)
        n_clips = _math.ceil((teaser_narr_dur - TEASER_XFADE) / (TEASER_CLIP_DUR - TEASER_XFADE))
        n_clips = min(max(n_clips, 3), TEASER_MAX_CLIPS)
        teaser_dur = (TEASER_CLIP_DUR - TEASER_XFADE) * (n_clips - 1) + TEASER_CLIP_DUR
        print(f"  テイザー検出: {teaser_dur:.1f}s（S00_teaser.wav）")
    else:
        print(f"  テイザーなし（S00_teaser.wav 未検出）")

    # 字幕オフセット = テイザー + チャンネルイントロ
    pre_scene_offset = teaser_dur + INTRO_DURATION

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

        scene_start = pre_scene_offset + scene_offsets[i] + NARR_DELAY
        text = scene["narration"].strip()
        sentences = split_sentences(text)

        if not sentences:
            continue

        # 語数比率でタイムスタンプを按分（チャンク単位）
        word_counts = [len(s.split()) for s in sentences]
        total_words = sum(word_counts)

        cursor = scene_start
        entry_count = 0
        for sentence, wc in zip(sentences, word_counts):
            ratio = wc / total_words if total_words > 0 else 1 / len(sentences)
            sentence_dur = narr_dur * ratio
            chunks = chunk_sentence(sentence)
            chunk_dur = sentence_dur / len(chunks)

            for chunk in chunks:
                start = cursor
                end = cursor + chunk_dur
                cursor = end

                srt_lines.append(str(idx))
                srt_lines.append(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}")
                srt_lines.append(chunk)
                srt_lines.append("")
                idx += 1
                entry_count += 1

        print(f"  S{scene['scene_id']:02d}: {entry_count}エントリ / {seconds_to_srt(scene_start)} → {seconds_to_srt(cursor)}")

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
