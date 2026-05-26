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
MIN_CLIP_FLOOR = 5.0
CROSSFADE_DURATION = 0.8

# テイザーイントロ設定（sc_video_gen.py と同値）
TEASER_CLIP_DUR = 2.5
TEASER_XFADE = 0.3
TEASER_MAX_CLIPS = 12


def split_sentences(text: str) -> list:
    """ナレーションを文単位に分割する。"""
    # ピリオド・感嘆符・疑問符の後ろで分割
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def detect_sentence_timestamps(wav_path: Path, sentences: list, total_dur: float) -> list:
    """WAV の無音検出で各文の (start, end) を推定する。

    silence_end（無音が明けた時刻）= 次の文の開始点として利用する。
    無音が不足する場合は語数比率フォールバックを返す。

    戻り値: [(sent_start, sent_end), ...] ― シーン音声開始からの秒数
    """
    n = len(sentences)
    word_counts = [len(s.split()) for s in sentences]
    total_words = sum(word_counts) or 1

    def ratio_fallback() -> list:
        result, cursor = [], 0.0
        for wc in word_counts:
            dur = total_dur * wc / total_words
            result.append((cursor, cursor + dur))
            cursor += dur
        return result

    if n <= 1:
        return [(0.0, total_dur)]

    # silencedetect: -35dB, 最小100ms（TTS文間の息継ぎを検出）
    r = subprocess.run(
        ["ffmpeg", "-i", str(wav_path),
         "-af", "silencedetect=n=-35dB:d=0.10",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )

    # silence_end = 無音明け = 次の文が始まる時刻
    silence_ends = []
    for line in r.stderr.splitlines():
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m:
            t = float(m.group(1))
            if 0.05 < t < total_dur - 0.05:
                silence_ends.append(t)

    # n-1 個の境界が必要。不足なら語数比率にフォールバック
    if len(silence_ends) < n - 1:
        return ratio_fallback()

    # 語数比率の期待境界に最近傍の silence_end を割り当て
    available = list(silence_ends)
    boundaries = [0.0]
    acc_words = 0
    for i in range(n - 1):
        acc_words += word_counts[i]
        expected = total_dur * acc_words / total_words
        best = min(available, key=lambda t: abs(t - expected))
        boundaries.append(best)
        available.remove(best)
    boundaries.append(total_dur)

    return [(boundaries[i], boundaries[i + 1]) for i in range(n)]


def chunk_sentence(text: str, max_chars: int = 42) -> list:
    """文を「最大2行・1行あたりmax_chars文字」のチャンクリストに分割する。
    1チャンクが2行を超える場合は次のチャンクへ繰り越す。"""
    words = text.split()
    chunks = []
    line1, line2 = [], []

    for word in words:
        if not line1:
            line1.append(word)
        elif not line2 and len(" ".join(line1 + [word])) <= max_chars:
            # line2 が空の間だけ line1 に追加（line2 に内容があれば line1 に戻らない）
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
        n_clips = max(n_clips, 3)  # 上限なし（sc_video_gen.py と同じ動作）
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
        min_dur = float(scene.get("duration_seconds", 10))
        wav = audio_dir / f"S{sid:02d}.wav"
        if wav.exists():
            narr_dur = probe_duration(wav)
            clip_dur = max(MIN_CLIP_FLOOR, narr_dur + NARR_DELAY + NARR_TAIL)
        else:
            narr_dur = 0.0
            clip_dur = min_dur
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

        # 無音検出で各文の実際のタイムスタンプを取得（失敗時は語数比率フォールバック）
        wav = audio_dir / f"S{scene['scene_id']:02d}.wav"
        sent_timestamps = detect_sentence_timestamps(wav, sentences, narr_dur)

        entry_count = 0
        last_cursor = scene_start
        for sentence, (sent_start, sent_end) in zip(sentences, sent_timestamps):
            sent_dur = sent_end - sent_start
            chunks = chunk_sentence(sentence)
            chunk_dur = sent_dur / len(chunks) if chunks else sent_dur
            cursor = scene_start + sent_start

            for chunk in chunks:
                start = cursor
                end = cursor + chunk_dur
                cursor = end
                last_cursor = end

                srt_lines.append(str(idx))
                srt_lines.append(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}")
                srt_lines.append(chunk)
                srt_lines.append("")
                idx += 1
                entry_count += 1

        print(f"  S{scene['scene_id']:02d}: {entry_count}エントリ / {seconds_to_srt(scene_start)} → {seconds_to_srt(last_cursor)}")

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
