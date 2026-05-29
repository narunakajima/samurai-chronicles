"""
sc_playlist_backfill.py — playlist_id が未登録のまま2件以上のエピソードがある
キャラクターのプレイリストを一括作成・バックフィルする。

使い方:
  python3 sc_playlist_backfill.py
  python3 sc_playlist_backfill.py --char nobunaga  # 特定キャラのみ
"""

import argparse
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHAR_PLAYLISTS_JSON = BASE_DIR / "character_playlists.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--char", help="特定キャラのみ処理（省略で全件）")
    args = parser.parse_args()

    from sc_sns_up import get_youtube_client
    from sc_playlist_manager import _create_playlist, _add_to_playlist, _save_data

    data = json.loads(CHAR_PLAYLISTS_JSON.read_text(encoding="utf-8"))
    youtube = get_youtube_client()

    targets = [
        (char, info)
        for char, info in data.items()
        if info["playlist_id"] is None and len(info["episodes"]) >= 2
        and (args.char is None or args.char == char)
    ]

    if not targets:
        print("バックフィルが必要なキャラクターはいません。")
        return

    print(f"\n対象: {len(targets)}キャラクター")
    for char, info in targets:
        display = info["display_name"]
        eps = info["episodes"]
        valid = [e for e in eps if e["video_id"]]
        print(f"\n  {display}: {len(eps)}エピソード（有効video_id: {len(valid)}件）")
        if not valid:
            print("    ⚠️  有効なvideo_idがありません。スキップ。")
            continue

        playlist_id = _create_playlist(youtube, display)
        data[char]["playlist_id"] = playlist_id
        added = 0
        for entry in eps:
            if entry["video_id"]:
                _add_to_playlist(youtube, playlist_id, entry["video_id"])
                added += 1
                print(f"    ✓ {entry['episode_id']} 追加")
            else:
                print(f"    ⚠️  {entry['episode_id']}: video_id なし スキップ")
        print(f"  ✓ {display}: プレイリスト作成 + {added}本追加完了")

    _save_data(data)
    print("\n✓ character_playlists.json 更新済み")

    # sanada_yukimura の ep008 バックフィル（プレイリストは既存）
    sy = data.get("sanada_yukimura", {})
    if sy.get("playlist_id") and args.char in (None, "sanada_yukimura"):
        # ep008がプレイリストに追加済みか確認できないため、追加を試みる
        ep008 = next((e for e in sy["episodes"] if e["episode_id"] == "ep008"), None)
        if ep008 and ep008["video_id"]:
            print(f"\n  Sanada Yukimura: ep008 をプレイリストに追加")
            _add_to_playlist(youtube, sy["playlist_id"], ep008["video_id"])
            print(f"  ✓ ep008 ({ep008['video_id']}) 追加完了")


if __name__ == "__main__":
    main()
