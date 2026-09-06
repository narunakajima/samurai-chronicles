"""
sc_retroactive_metadata_push.py — 既存公開済み動画のメタデータを一括で遡及修正する
（Fable監査2026-09-07対応）

対象:
  1. selfDeclaredMadeForKids / containsSyntheticMedia の明示送信
     （従来チャンネル既定値に依存し未送信だった）
  2. 配信頻度表記の統一（"every day" → "every Tuesday, Thursday & Saturday"）
     ※ episodes/ep{NNN}.json の youtube_description は本スクリプト実行前に
       ローカル側で既に修正済みであること（sc_retroactive_metadata_push.py は
       ローカルJSONの内容をそのままYouTubeへ反映するだけで、テキスト修正は行わない）
  3. CC BY BGMクレジットの欠落分（sc_bgm_credit_audit.py --fix で
     ローカルJSONに追記済みであること）

本スクリプトは実際に公開中のYouTube動画（本編94本＋Shorts）のsnippet/statusを
videos.update() で書き換える。**必ず --dry-run で対象を確認してから実行すること。**

使い方:
  python3 sc_retroactive_metadata_push.py --dry-run   # 対象一覧の確認のみ
  python3 sc_retroactive_metadata_push.py             # 実際にYouTubeへ反映
  python3 sc_retroactive_metadata_push.py --episode ep050  # 特定の1話のみ
"""

import argparse
import glob
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="対象一覧を表示するだけで更新しない")
    parser.add_argument("--episode", help="特定のエピソードIDのみ処理（例: ep050）")
    args = parser.parse_args()

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

    status_body = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}

    for t in targets:
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

    print("\n✓ 完了")


if __name__ == "__main__":
    main()
