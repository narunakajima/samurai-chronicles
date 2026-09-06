"""
sc_playlist_rescan_backfill.py — Fable監査(2026-09-07)で判明した
sc_playlist_manager.py の予約公開スキップバグ（ep051以降のキャラクター登場が
character_playlists.json に一切記録されていなかった問題）の遡及バックフィル。

処理内容:
  1. episodes/ep*.json を全件スキャンし、character_ref（teaserシーンを除く）を
     character_playlists.json の記録と突き合わせ、欠落しているエピソードを追記する
  2. playlist_id が未登録で2回以上登場のキャラクターはプレイリストを新規作成し、
     公開済みエピソードを追加する
  3. 既にplaylist_idを持つキャラクターについては、欠落エピソードのうち
     公開済みのものだけをプレイリストに追加する

⚠️ --dry-run なしの実行はYouTube上に実際のプレイリストを作成・動画追加する。

安全対策（2026-09-08追加）:
  - 実行前に character_playlists.json を backups/ にタイムスタンプ付きでコピーする
  - 作成したプレイリストID・追加したplaylistItem IDを逐次
    backups/playlist_backfill_{timestamp}.json に記録する
  - 問題があれば --undo でこのログを使い、追加したplaylistItemを削除し
    character_playlists.json をバックアップから復元できる
    （新規作成したプレイリスト自体は空になるだけで残る。不要なら手動で削除すること）

使い方:
  python3 sc_playlist_rescan_backfill.py --dry-run   # 何が追加されるか確認のみ
  python3 sc_playlist_rescan_backfill.py              # 実際にYouTubeへ反映
  python3 sc_playlist_rescan_backfill.py --undo backups/playlist_backfill_20260908_120000.json
                                                       # 追加分を取り消す
"""

import argparse
import glob
import json
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHAR_PLAYLISTS_JSON = BASE_DIR / "character_playlists.json"
BACKUP_DIR = BASE_DIR / "backups"


def _video_id_from_url(url: str):
    if not url:
        return None
    return url.rstrip("/").split("/")[-1]


def rescan_missing_entries() -> dict:
    """episodes/ep*.json を全件スキャンし、character_playlists.json に
    欠落しているキャラクター登場エントリを返す（episode_id昇順）。
    戻り値: {char: [{"episode_id":..., "video_id":...}, ...]}（追加分のみ）
    """
    data = (
        json.loads(CHAR_PLAYLISTS_JSON.read_text(encoding="utf-8"))
        if CHAR_PLAYLISTS_JSON.exists()
        else {}
    )
    recorded = {
        char: {e["episode_id"] for e in info.get("episodes", [])}
        for char, info in data.items()
    }

    missing = {}
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        ep = json.loads(Path(f).read_text(encoding="utf-8"))
        episode_id = ep.get("episode_id")
        video_id = _video_id_from_url(ep.get("youtube_url", ""))
        chars = set()
        for scene in ep.get("scenes", []):
            if scene.get("type") == "teaser":
                continue
            c = scene.get("character_ref")
            if c:
                chars.add(c)
        for char in chars:
            if episode_id in recorded.get(char, set()):
                continue
            missing.setdefault(char, []).append(
                {"episode_id": episode_id, "video_id": video_id}
            )
    return missing


def _log_action(log_path: Path, entry: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    data.append(entry)
    log_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def undo(log_file: Path):
    from sc_sns_up import get_youtube_client
    youtube = get_youtube_client()

    log = json.loads(log_file.read_text(encoding="utf-8"))
    added_items = [e for e in log if e["action"] == "add_item"]
    created_playlists = [e for e in log if e["action"] == "create_playlist"]
    backup_ref = next((e["backup_file"] for e in log if e.get("backup_file")), None)

    print(f"取り消し対象: playlistItem {len(added_items)}件、新規プレイリスト{len(created_playlists)}件\n")

    for e in added_items:
        try:
            youtube.playlistItems().delete(id=e["playlist_item_id"]).execute()
            print(f"  ✓ 削除: {e['char']} / {e['episode_id']} (playlistItem={e['playlist_item_id']})")
        except Exception as ex:
            print(f"  ⚠️ 削除失敗: {e['char']} / {e['episode_id']} — {ex}")

    if created_playlists:
        print("\n以下は今回新規作成したプレイリストです（動画は上記で削除済みのため空になります）。")
        print("完全に削除したい場合は手動でYouTube Studioから削除してください:")
        for e in created_playlists:
            print(f"  - {e['char']}: https://www.youtube.com/playlist?list={e['playlist_id']}")

    if backup_ref and Path(backup_ref).exists():
        shutil.copy(backup_ref, CHAR_PLAYLISTS_JSON)
        print(f"\n✓ character_playlists.json を {backup_ref} から復元しました。")
    else:
        print("\n⚠️ character_playlists.json のバックアップ参照が見つかりません。手動確認してください。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="変更内容を表示するだけでJSON更新・YouTube反映は行わない",
    )
    parser.add_argument(
        "--undo", metavar="LOG_FILE",
        help="指定した実行ログを使い、追加したplaylistItemを削除しJSONを復元する",
    )
    args = parser.parse_args()

    if args.undo:
        undo(Path(args.undo))
        return

    from sc_playlist_manager import (
        CHAR_DISPLAY_NAMES, _create_playlist, _add_to_playlist,
        _is_published, _load_episode_json,
    )

    missing = rescan_missing_entries()
    if not missing:
        print("欠落しているキャラクター登場エントリはありません。")
        return

    print(f"欠落エントリを検出: {sum(len(v) for v in missing.values())}件・{len(missing)}キャラクター\n")
    for char, entries in sorted(missing.items()):
        display = CHAR_DISPLAY_NAMES.get(char, char.replace("_", " ").title())
        print(f"  {display} ({char}): {[e['episode_id'] for e in entries]}")

    if args.dry_run:
        print("\n--dry-run のためJSON更新・YouTube反映は行いません。")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"character_playlists_{timestamp}.json"
    log_path = BACKUP_DIR / f"playlist_backfill_{timestamp}.json"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if CHAR_PLAYLISTS_JSON.exists():
        shutil.copy(CHAR_PLAYLISTS_JSON, backup_path)
    print(f"\nバックアップ: {backup_path}")
    print(f"実行ログ: {log_path}")
    _log_action(log_path, {"action": "backup", "backup_file": str(backup_path)})

    data = (
        json.loads(CHAR_PLAYLISTS_JSON.read_text(encoding="utf-8"))
        if CHAR_PLAYLISTS_JSON.exists()
        else {}
    )
    for char, entries in missing.items():
        if char not in data:
            display = CHAR_DISPLAY_NAMES.get(char, char.replace("_", " ").title())
            data[char] = {"display_name": display, "playlist_id": None, "episodes": []}
        data[char]["episodes"].extend(entries)
        data[char]["episodes"].sort(key=lambda e: e["episode_id"])

    CHAR_PLAYLISTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n✓ character_playlists.json に欠落エントリを反映しました。")

    from sc_sns_up import get_youtube_client
    youtube = get_youtube_client()

    for char, info in data.items():
        eps = info["episodes"]
        if len(eps) < 2:
            continue
        display = info["display_name"]

        if info["playlist_id"] is None:
            print(f"\n  {display}: プレイリスト新規作成")
            playlist_id = _create_playlist(youtube, display)
            info["playlist_id"] = playlist_id
            _log_action(log_path, {
                "action": "create_playlist", "char": char, "playlist_id": playlist_id,
            })
            added = 0
            for entry in eps:
                vid = entry.get("video_id")
                if not vid:
                    continue
                ep_data = _load_episode_json(entry["episode_id"])
                if ep_data and not _is_published(ep_data):
                    continue
                try:
                    resp = _add_to_playlist(youtube, playlist_id, vid)
                    _log_action(log_path, {
                        "action": "add_item", "char": char, "episode_id": entry["episode_id"],
                        "playlist_id": playlist_id, "playlist_item_id": resp["id"],
                    })
                    added += 1
                except Exception as e:
                    print(f"     ⚠️  {entry['episode_id']}: 追加失敗 — {e}")
            print(f"     ✓ {added}本追加")
        else:
            playlist_id = info["playlist_id"]
            resp = youtube.playlistItems().list(
                part="snippet", playlistId=playlist_id, maxResults=50
            ).execute()
            actual = {
                item["snippet"]["resourceId"]["videoId"] for item in resp.get("items", [])
            }
            added = 0
            for entry in eps:
                vid = entry.get("video_id")
                if not vid or vid in actual:
                    continue
                ep_data = _load_episode_json(entry["episode_id"])
                if ep_data and not _is_published(ep_data):
                    continue
                try:
                    add_resp = _add_to_playlist(youtube, playlist_id, vid)
                    _log_action(log_path, {
                        "action": "add_item", "char": char, "episode_id": entry["episode_id"],
                        "playlist_id": playlist_id, "playlist_item_id": add_resp["id"],
                    })
                    added += 1
                    print(f"  {display}: {entry['episode_id']} を既存プレイリストに追加")
                except Exception as e:
                    print(f"     ⚠️  {entry['episode_id']}: 追加失敗 — {e}")
            if added:
                print(f"  ✓ {display}: {added}本を既存プレイリストに追加")

    CHAR_PLAYLISTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✓ 完了。問題があれば次のコマンドで取り消せます:")
    print(f"  python3 sc_playlist_rescan_backfill.py --undo {log_path}")


if __name__ == "__main__":
    main()
