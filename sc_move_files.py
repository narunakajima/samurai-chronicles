"""
sc_move_files.py — デスクトップからGoogle Driveへのファイル移動

使い方:
  python3 sc_move_files.py --episode ep001

移動対象:
  1. ~/Desktop/ep001*.wav        → Drive/ep001/audio/
  2. ~/Desktop/BGM_candidate_*.mp3 (1曲のみ) → Drive/ep001/audio/ep001-BGM.mp3
  3. ~/Desktop/ep001_制作確認書*.txt → Drive/ep001/
"""

import argparse
import shutil
import sys
from pathlib import Path

DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)
DESKTOP = Path.home() / "Desktop"


def move(src: Path, dst: Path, label: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    print(f"  ✓ {label}: {src.name} → {dst.relative_to(Path.home())}")


def run(episode_id: str):
    ep_dir = DRIVE_BASE / episode_id
    audio_dir = ep_dir / "audio"

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — デスクトップ → Drive 移動")
    print(f"{'━'*60}\n")

    moved = 0

    # 1. WAVファイル
    wav_files = sorted(DESKTOP.glob(f"{episode_id}*.wav"))
    for wav in wav_files:
        move(wav, audio_dir / wav.name, "WAV")
        moved += 1
    if not wav_files:
        print(f"  ℹ️  WAVなし（スキップ）")

    # 2. BGM（BGM_candidate_*.mp3 が残り1曲）
    bgm_candidates = sorted(DESKTOP.glob("BGM_candidate_*.mp3"))
    if len(bgm_candidates) == 1:
        dest_bgm = audio_dir / f"{episode_id}-BGM.mp3"
        move(bgm_candidates[0], dest_bgm, "BGM")
        moved += 1
    elif len(bgm_candidates) > 1:
        print(f"  ⚠️  BGM候補が{len(bgm_candidates)}曲あります。1曲だけ残してから再実行してください。")
        for f in bgm_candidates:
            print(f"     - {f.name}")
    else:
        print(f"  ℹ️  BGM候補なし（スキップ）")

    # 3. 制作確認書
    review_files = sorted(DESKTOP.glob(f"{episode_id}_制作確認書*.txt"))
    for f in review_files:
        move(f, ep_dir / f.name, "制作確認書")
        moved += 1
    if not review_files:
        print(f"  ℹ️  制作確認書なし（スキップ）")

    print(f"\n  合計 {moved} ファイルを移動しました。\n")


def cli():
    parser = argparse.ArgumentParser(description="デスクトップ → Drive ファイル移動")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    args = parser.parse_args()

    ep_id = args.episode.strip().lower()
    if not ep_id.startswith("ep"):
        ep_id = f"ep{ep_id.zfill(3)}"

    run(ep_id)


if __name__ == "__main__":
    cli()
