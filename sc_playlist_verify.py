"""
sc_playlist_verify.py — character_playlists.json と YouTube 実データの整合性検証・自動修正

背景:
  手動でのプレイリスト削除・再作成や、複数マシン間のマージによって
  character_playlists.json に記録された playlist_id が古い／実在しない
  状態になることがある（実数とのズレ）。

  このスクリプトは YouTube API から実際のプレイリスト一覧と所属動画を取得し、
  character_playlists.json と突き合わせて以下を検出・自動修正する:

    1. 記録された playlist_id が YouTube 上に実在しない
       → 所属動画（video_id）の重なりで同一プレイリストの再作成を検出し、
         新IDに自動修正。一致するものがなければ null に修正
    2. プレイリストは実在するが、ID が変わっている
       → 1と同じロジックで自動修正
    3. 実在するが character_playlists.json に記録されていないプレイリスト
       → 警告として表示（自動修正はしない／手動確認が必要なため）

  修正があった場合は character_playlists.json を上書きし、サイトを再生成する。

使い方:
  python3 sc_playlist_verify.py             # 検証＋自動修正
  python3 sc_playlist_verify.py --check-only  # 検証のみ（修正しない）
"""

import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHAR_PLAYLISTS_JSON = BASE_DIR / "character_playlists.json"


def _load_data() -> dict:
    if CHAR_PLAYLISTS_JSON.exists():
        return json.loads(CHAR_PLAYLISTS_JSON.read_text(encoding="utf-8"))
    return {}


def _save_data(data: dict):
    CHAR_PLAYLISTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _fetch_youtube_playlists(youtube) -> dict:
    """チャンネルの全プレイリストとその所属動画IDを取得する。
    戻り値: {playlist_id: {"title": str, "video_ids": set[str]}}
    """
    result = {}
    req = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
    while req:
        res = req.execute()
        for item in res.get("items", []):
            pid = item["id"]
            title = item["snippet"]["title"]
            result[pid] = {"title": title, "video_ids": set()}
        req = youtube.playlists().list_next(req, res)

    for pid, info in result.items():
        req = youtube.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50)
        while req:
            res = req.execute()
            for item in res.get("items", []):
                info["video_ids"].add(item["contentDetails"]["videoId"])
            req = youtube.playlistItems().list_next(req, res)

    return result


def verify_and_fix(youtube, auto_fix: bool = True, verbose: bool = True) -> dict:
    """検証を実行し、必要なら character_playlists.json を修正する。

    戻り値: {"fixed": [...], "nulled": [...], "orphans": [...], "ok": bool}
    """
    data = _load_data()
    yt_playlists = _fetch_youtube_playlists(youtube)
    yt_ids = set(yt_playlists.keys())

    fixed = []   # (char_key, old_id, new_id)
    nulled = []  # (char_key, old_id)
    matched_yt_ids = set()

    for char_key, char_data in data.items():
        pid = char_data.get("playlist_id")
        if not pid:
            continue

        if pid in yt_ids:
            matched_yt_ids.add(pid)
            continue

        # 記録されたIDがYouTube上に存在しない → 動画の重なりで再作成を検出
        recorded_vids = {e["video_id"] for e in char_data.get("episodes", []) if e.get("video_id")}
        best_match = None
        best_overlap = 0
        for yt_pid, info in yt_playlists.items():
            if yt_pid in matched_yt_ids:
                continue
            overlap = len(recorded_vids & info["video_ids"])
            if overlap > 0 and overlap > best_overlap:
                best_overlap = overlap
                best_match = yt_pid

        if best_match:
            if verbose:
                print(f"  🔧 {char_key}（{char_data['display_name']}）: "
                      f"playlist_id を修正 {pid} → {best_match}（動画{best_overlap}件一致）")
            if auto_fix:
                char_data["playlist_id"] = best_match
            fixed.append((char_key, pid, best_match))
            matched_yt_ids.add(best_match)
        else:
            if verbose:
                print(f"  ❌ {char_key}（{char_data['display_name']}）: "
                      f"playlist_id {pid} はYouTube上に存在せず、一致するプレイリストもなし → null に修正")
            if auto_fix:
                char_data["playlist_id"] = None
            nulled.append((char_key, pid))

    # 実在するがJSONに記録されていないプレイリスト（孤児）
    orphans = []
    recorded_ids = {c.get("playlist_id") for c in data.values() if c.get("playlist_id")}
    for yt_pid, info in yt_playlists.items():
        if yt_pid not in recorded_ids and yt_pid not in matched_yt_ids:
            orphans.append((yt_pid, info["title"]))
            if verbose:
                print(f"  ⚠️  未記録のプレイリストがYouTube上に存在: {info['title']} ({yt_pid})")

    if not fixed and not nulled and not orphans:
        if verbose:
            print(f"  ✅ 整合性チェック OK — character_playlists.json と YouTube 実データは一致（{len(yt_ids)}件）")

    if auto_fix and (fixed or nulled):
        _save_data(data)
        if verbose:
            print(f"  💾 character_playlists.json を更新しました")
        try:
            from sc_build_site import build as build_site
            build_site()
            if verbose:
                print(f"  🔄 サイトを再生成しました")
        except Exception as e:
            if verbose:
                print(f"  ⚠️  サイト再生成でエラー: {e}")

    return {"fixed": fixed, "nulled": nulled, "orphans": orphans,
            "ok": not fixed and not nulled and not orphans}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="検証のみ（修正しない）")
    args = parser.parse_args()

    from sc_sns_up import get_youtube_client
    youtube = get_youtube_client()

    print("━" * 60)
    print("  プレイリスト整合性検証（character_playlists.json ⇔ YouTube）")
    print("━" * 60)

    result = verify_and_fix(youtube, auto_fix=not args.check_only)

    print("━" * 60)
    if args.check_only:
        n = len(result["fixed"]) + len(result["nulled"]) + len(result["orphans"])
        print(f"  検証結果: {'問題なし' if n == 0 else f'{n}件の不整合を検出（--check-only のため未修正）'}")
    else:
        n = len(result["fixed"]) + len(result["nulled"])
        print(f"  修正結果: {'修正なし（整合済み）' if n == 0 else f'{n}件を自動修正'}")
        if result["orphans"]:
            print(f"  ⚠️  未記録プレイリスト {len(result['orphans'])}件 — 手動確認が必要です")
    print("━" * 60)


if __name__ == "__main__":
    main()
