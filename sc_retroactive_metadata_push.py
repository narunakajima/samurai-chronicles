"""
sc_retroactive_metadata_push.py — 既存公開済み動画のメタデータを一括で遡及修正する
（Fable監査2026-09-07対応）

対象:
  1. selfDeclaredMadeForKids / containsSyntheticMedia の明示送信
     （従来チャンネル既定値に依存し未送信だった）
  2. 配信頻度表記の統一（"every day" → "every Tuesday, Thursday & Saturday"）
     ※ episodes/ep{NNN}.json の youtube_description は本スクリプト実行前に
       ローカル側で既に修正済みであること（本スクリプトはローカルJSONの内容を
       そのままYouTubeへ反映するだけで、テキスト修正は行わない）
  3. CC BY BGMクレジットの欠落分（sc_bgm_credit_audit.py --fix で
     ローカルJSONに追記済みであること）

本スクリプトは実際に公開中のYouTube動画（本編94本＋Shorts）のsnippet/statusを
videos.update() で書き換える。**必ず --dry-run で対象を確認してから実行すること。**

⚠️ 安全対策（2026-09-08追加）: 各動画を更新する直前に、更新前のsnippet/statusを
videos.list() で取得し `backups/metadata_push_{timestamp}.json` に保存する。
不具合が起きた場合は --restore でこのバックアップから元の状態に戻せる。
バックアップへの書き込みは1件ごとに逐次行うため、途中で中断してもそこまでの分は復旧できる。

使い方:
  python3 sc_retroactive_metadata_push.py --dry-run   # 対象一覧の確認のみ
  python3 sc_retroactive_metadata_push.py             # 実際にYouTubeへ反映（自動でバックアップ作成）
  python3 sc_retroactive_metadata_push.py --episode ep050  # 特定の1話のみ
  python3 sc_retroactive_metadata_push.py --restore backups/metadata_push_20260908_120000.json
                                                        # バックアップから復元
"""

import argparse
import glob
import json
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "backups"


def _video_id_from_url(url: str):
    if not url:
        return None
    return url.rstrip("/").split("/")[-1]


def _shorts_description(ep: dict, main_id: str) -> str:
    """sc_sns_up.py run() のShorts概要欄組み立てロジックと同一（修正後の文言）。"""
    hook_lines = ep.get("shorts_hook_lines", [])
    hook_text = "\n".join(hook_lines) if hook_lines else ep.get("episode_title", "")
    return (
        f"{hook_text}\n\n"
        f"▶ Full episode: https://youtu.be/{main_id}\n\n"
        f"** Subscribe for new episodes every Tuesday, Thursday & Saturday:\n"
        f"https://www.youtube.com/@Samurai-Chronicles-JP"
    )


def collect_targets(only_episode: str = None):
    targets = []
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        ep = json.loads(Path(f).read_text(encoding="utf-8"))
        episode_id = ep.get("episode_id")
        if only_episode and episode_id != only_episode:
            continue
        main_id = _video_id_from_url(ep.get("youtube_url", ""))
        if not main_id:
            continue  # 未公開
        shorts_id = _video_id_from_url(ep.get("shorts_url", ""))
        targets.append({
            "episode_id": episode_id,
            "main_id": main_id,
            "shorts_id": shorts_id,
            "title": ep.get("youtube_title"),
            "description": ep.get("youtube_description", ""),
            "tags": ep.get("youtube_tags", []),
            "ep": ep,
        })
    return targets


def _fetch_current(youtube, video_id: str) -> dict:
    """更新前のsnippet/statusを取得する（バックアップ用）。"""
    resp = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        return {}
    return {"snippet": items[0]["snippet"], "status": items[0]["status"]}


def _append_backup(backup_path: Path, entry: dict):
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(backup_path.read_text(encoding="utf-8")) if backup_path.exists() else []
    data.append(entry)
    backup_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def restore(backup_file: Path):
    from sc_sns_up import get_youtube_client
    youtube = get_youtube_client()

    data = json.loads(backup_file.read_text(encoding="utf-8"))
    print(f"復元対象: {len(data)}件（{backup_file}）\n")
    for entry in data:
        video_id = entry["video_id"]
        before = entry["before"]
        if not before:
            print(f"  ⚠️ {video_id}: バックアップ時点で取得できていなかったためスキップ")
            continue
        try:
            youtube.videos().update(
                part="snippet,status",
                body={
                    "id": video_id,
                    "snippet": before["snippet"],
                    "status": {
                        k: v for k, v in before["status"].items()
                        if k in ("selfDeclaredMadeForKids", "containsSyntheticMedia",
                                  "privacyStatus", "publishAt")
                    },
                },
            ).execute()
            print(f"  ✓ {video_id} ({entry.get('episode_id', '')}/{entry.get('kind', '')}): 復元完了")
        except Exception as e:
            print(f"  ⚠️ {video_id}: 復元失敗 — {e}")
        time.sleep(0.5)
    print("\n✓ 復元処理完了")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="対象一覧を表示するだけで更新しない")
    parser.add_argument("--episode", help="特定のエピソードIDのみ処理（例: ep050）")
    parser.add_argument("--restore", metavar="BACKUP_FILE",
                        help="指定したバックアップファイルの内容にYouTube側を戻す")
    args = parser.parse_args()

    if args.restore:
        restore(Path(args.restore))
        return

    targets = collect_targets(args.episode)
    if not targets:
        print("対象の公開済みエピソードがありません。")
        return

    print(f"対象: 本編{len(targets)}本（うちShortsあり: {sum(1 for t in targets if t['shorts_id'])}本）\n")
    for t in targets:
        print(f"  {t['episode_id']}: main={t['main_id']}  shorts={t['shorts_id'] or '(なし)'}")

    if args.dry_run:
        print("\n--dry-run のためYouTubeへの反映は行いません。")
        return

    from sc_sns_up import get_youtube_client
    youtube = get_youtube_client()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"metadata_push_{timestamp}.json"
    print(f"\nバックアップ先: {backup_path}")

    status_body = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}

    for t in targets:
        before = _fetch_current(youtube, t["main_id"])
        _append_backup(backup_path, {
            "video_id": t["main_id"], "episode_id": t["episode_id"],
            "kind": "main", "before": before,
        })
        try:
            youtube.videos().update(
                part="snippet,status",
                body={
                    "id": t["main_id"],
                    "snippet": {
                        "title": t["title"],
                        "description": t["description"],
                        "tags": t["tags"],
                        "categoryId": "27",
                        "defaultLanguage": "en",
                        "defaultAudioLanguage": "en",
                    },
                    "status": status_body,
                },
            ).execute()
            print(f"  ✓ {t['episode_id']} 本編 ({t['main_id']}): 更新完了")
        except Exception as e:
            print(f"  ⚠️ {t['episode_id']} 本編 ({t['main_id']}): 更新失敗 — {e}")
        time.sleep(0.5)

        if t["shorts_id"]:
            before_s = _fetch_current(youtube, t["shorts_id"])
            _append_backup(backup_path, {
                "video_id": t["shorts_id"], "episode_id": t["episode_id"],
                "kind": "shorts", "before": before_s,
            })
            shorts_desc = _shorts_description(t["ep"], t["main_id"])
            try:
                youtube.videos().update(
                    part="snippet,status",
                    body={
                        "id": t["shorts_id"],
                        "snippet": {
                            "title": f"{t['title']} #Shorts",
                            "description": shorts_desc,
                            "tags": t["tags"] + ["shorts"],
                            "categoryId": "27",
                            "defaultLanguage": "en",
                            "defaultAudioLanguage": "en",
                        },
                        "status": status_body,
                    },
                ).execute()
                print(f"  ✓ {t['episode_id']} Shorts ({t['shorts_id']}): 更新完了")
            except Exception as e:
                print(f"  ⚠️ {t['episode_id']} Shorts ({t['shorts_id']}): 更新失敗 — {e}")
            time.sleep(0.5)

    print(f"\n✓ 完了。バックアップ: {backup_path}")
    print(f"  問題があれば次のコマンドで復元できます:")
    print(f"  python3 sc_retroactive_metadata_push.py --restore {backup_path}")


if __name__ == "__main__":
    main()
