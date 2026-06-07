"""
sc_sns_up.py — Samurai Chronicles YouTube アップロード

使い方:
  python3 sc_sns_up.py --episode ep001              # 次の空き 03:00 JST に自動予約
  python3 sc_sns_up.py --episode ep001 --now        # 即時公開
  python3 sc_sns_up.py --episode ep001 --publish-at "2026-06-01 20:00"  # 日時指定

デフォルト動作:
  毎日 03:00 JST に1本ずつ公開。
  すでに予約済みのエピソードがある場合は翌日以降の空きスロットを自動割り当て。

認証: ~/.claude/secrets/yt_client_secrets.json（Lamps Whisper と共用）
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

SAMURAI_CHANNEL_ID = "UCN1-TUxX_2UumGm3OKpmncg"  # Samurai Chronicles チャンネルID

SECRETS_DIR = Path.home() / ".claude" / "secrets"
YT_CLIENT_SECRETS = SECRETS_DIR / "yt_client_secrets.json"
YT_TOKEN = SECRETS_DIR / "yt_token_sc.json"

BASE_DIR = Path(__file__).parent
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)


def get_youtube_client():
    creds = None
    if YT_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(YT_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not YT_CLIENT_SECRETS.exists():
                print(f"❌ 認証ファイルが見つかりません: {YT_CLIENT_SECRETS}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(YT_CLIENT_SECRETS), SCOPES)
            creds = flow.run_local_server(port=8081, prompt="select_account consent")
        YT_TOKEN.parent.mkdir(parents=True, exist_ok=True)
        YT_TOKEN.write_text(creds.to_json())
    youtube = build("youtube", "v3", credentials=creds)

    # チャンネル確認（誤チャンネルアップロード防止）
    ch_resp = youtube.channels().list(part="snippet", mine=True).execute()
    ch_items = ch_resp.get("items", [])
    if ch_items:
        ch_id = ch_items[0]["id"]
        ch_name = ch_items[0]["snippet"]["title"]
        print(f"  認証チャンネル: {ch_name} ({ch_id})")
        if ch_id != SAMURAI_CHANNEL_ID:
            print(f"  ❌ エラー: Samurai Chronicles チャンネルではありません！")
            print(f"  rm ~/.claude/secrets/yt_token_sc.json で再認証してください。")
            YT_TOKEN.unlink(missing_ok=True)
            sys.exit(1)
    else:
        print("  警告: チャンネル情報を取得できませんでした。")

    return youtube


JST = ZoneInfo("Asia/Tokyo")
PUBLISH_HOUR_JST = 3  # 毎日 03:00 JST に公開


def find_next_publish_slot() -> str:
    """
    次の空き 03:00 JST スロットを返す（"YYYY-MM-DD HH:MM" JST 形式）。

    配信曜日: 火〜土（月・日はスキップ）
    - episodes/*.json の scheduled_at を読んで使用済み日付を収集
    - 今日の 03:00 JST が未来 → 今日を候補に、過去 → 明日を候補に
    - 月・日 および 使用済み日付を避けて最初の空き日を返す
    """
    # 配信可能な曜日: 火(1), 水(2), 木(3), 金(4), 土(5)
    PUBLISH_WEEKDAYS = {1, 2, 3, 4, 5}  # 0=月, 6=日 はスキップ

    now_jst = datetime.now(JST)

    # 使用済みスロット（date）を収集
    used_dates: set = set()
    for ep_file in (BASE_DIR / "episodes").glob("ep*.json"):
        if ep_file.stat().st_size == 0:
            continue
        try:
            ep = json.loads(ep_file.read_text(encoding="utf-8"))
            raw = ep.get("scheduled_at", "")
            if raw:
                used_dates.add(datetime.strptime(raw[:10], "%Y-%m-%d").date())
        except (json.JSONDecodeError, ValueError):
            continue

    # 最初の候補: 今日の 03:00 JST
    candidate = now_jst.replace(hour=PUBLISH_HOUR_JST, minute=0, second=0, microsecond=0)
    if candidate <= now_jst:
        candidate += timedelta(days=1)

    # 配信曜日 かつ 使用済みでない日を探す
    while (candidate.weekday() not in PUBLISH_WEEKDAYS) or (candidate.date() in used_dates):
        candidate += timedelta(days=1)

    return candidate.strftime("%Y-%m-%d %H:%M")


def parse_publish_at(publish_at_str: str) -> str:
    """
    公開日時文字列を RFC 3339（UTC）に変換して返す。
    入力例:
      "2026-06-01 20:00"    → JST として解釈
      "2026-06-01 20:00 JST"
      "2026-06-01 11:00 UTC"
    """
    s = publish_at_str.strip()

    # タイムゾーン指定の分離
    if s.upper().endswith("UTC"):
        tz = timezone.utc
        s = s[:-3].strip()
    else:
        # JST（デフォルト）
        if s.upper().endswith("JST"):
            s = s[:-3].strip()
        tz = ZoneInfo("Asia/Tokyo")

    # パース
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            dt_naive = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"日時フォーマットが解析できません: {publish_at_str!r}\n"
                         "例: '2026-06-01 20:00' (JST) または '2026-06-01 11:00 UTC'")

    dt_aware = dt_naive.replace(tzinfo=tz)
    return dt_aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upload_video(youtube, video_path: Path, title: str, description: str,
                 tags: list, publish_at: Optional[str] = None) -> str:
    if publish_at:
        publish_at_rfc = parse_publish_at(publish_at)
        status_body = {"privacyStatus": "private", "publishAt": publish_at_rfc}
        print(f"  アップロード中（予約公開: {publish_at}）: {video_path.name} ...")
    else:
        status_body = {"privacyStatus": "public"}
        print(f"  アップロード中: {video_path.name} ...")

    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "27",  # Education
                "defaultLanguage": "en",
            },
            "status": status_body,
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%", end="\r")
    video_id = response["id"]
    if publish_at:
        print(f"  ✓ 完了（予約公開: {publish_at}）: https://youtu.be/{video_id}")
    else:
        print(f"  ✓ 完了（即時公開）: https://youtu.be/{video_id}")
    return video_id


def upload_thumbnail(youtube, video_id: str, thumbnail_path: Path):
    print(f"  サムネイルアップロード中: {thumbnail_path.name} ...")
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
    ).execute()
    print(f"  ✓ サムネイル完了")


def upload_caption(youtube, video_id: str, srt_path: Path):
    print(f"  字幕アップロード中: {srt_path.name} ...")
    youtube.captions().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "language": "en",
                "name": "English",
                "isDraft": False,
            }
        },
        media_body=MediaFileUpload(str(srt_path), mimetype="application/octet-stream"),
    ).execute()
    print(f"  ✓ 字幕完了")


def run(episode_id: str, publish_at: Optional[str] = None, publish_now: bool = False):
    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    out_dir = DRIVE_BASE / episode_id / "output"
    main_video = out_dir / f"Samurai Chronicles {episode_id}.mp4"
    shorts_video = out_dir / f"{episode_id}_shorts.mp4"
    srt_file = out_dir / f"{episode_id}.srt"
    thumbnail_file = DRIVE_BASE / episode_id / f"{episode_id}_thumbnail.png"

    title = ep["youtube_title"]
    description = ep["youtube_description"]
    tags = ep.get("youtube_tags", [])

    # 公開日時の決定
    if publish_now:
        publish_at = None  # 即時公開
        publish_label = "即時公開"
    elif publish_at:
        publish_label = f"予約公開: {publish_at} JST"
    else:
        publish_at = find_next_publish_slot()
        publish_label = f"予約公開: {publish_at} JST（自動）"

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — YouTube アップロード（{publish_label}）")
    print(f"{'━'*60}\n")

    for path, label in [(main_video, "本編"), (shorts_video, "Shorts")]:
        if not path.exists():
            print(f"❌ {label}動画が見つかりません: {path}")
            sys.exit(1)

    youtube = get_youtube_client()

    # 本編
    print("【本編】")
    main_id = upload_video(youtube, main_video, title, description, tags, publish_at)
    if srt_file.exists():
        upload_caption(youtube, main_id, srt_file)
    else:
        print(f"  ⚠️  字幕ファイルなし（スキップ）")
    if thumbnail_file.exists():
        try:
            upload_thumbnail(youtube, main_id, thumbnail_file)
        except Exception as e:
            print(f"  ⚠️  サムネイルスキップ（YouTube Studioで手動設定してください）: {e}")
    else:
        print(f"  ⚠️  サムネイルなし（スキップ）: {thumbnail_file.name}")

    time.sleep(2)

    # Shorts
    print("\n【Shorts】")
    hook_lines = ep.get("shorts_hook_lines", [])
    hook_text = "\n".join(hook_lines) if hook_lines else ep.get("episode_title", "")
    shorts_description = (
        f"{hook_text}\n\n"
        f"▶ Full episode: https://youtu.be/{main_id}\n\n"
        f"** Subscribe for new episodes every day:\n"
        f"https://www.youtube.com/@Samurai-Chronicles-JP"
    )
    shorts_id = upload_video(youtube, shorts_video,
                             f"{title} #Shorts", shorts_description, tags + ["shorts"],
                             publish_at)

    # youtube_url / shorts_url / scheduled_at を ep.json に書き戻す
    ep["youtube_url"] = f"https://youtu.be/{main_id}"
    ep["shorts_url"] = f"https://youtu.be/{shorts_id}"
    ep["scheduled_at"] = publish_at if publish_at else ""
    with open(ep_json, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)
    print(f"  ✓ ep.json に youtube_url / shorts_url / scheduled_at を保存しました")

    print(f"\n{'━'*60}")
    print(f"  ✓ アップロード完了（{publish_label}）")
    print(f"  本編:   https://youtu.be/{main_id}")
    print(f"  Shorts: https://youtu.be/{shorts_id}")
    print(f"{'━'*60}\n")

    # キャラクタープレイリスト自動更新
    print(f"{'━'*60}")
    print(f"  プレイリスト処理")
    print(f"{'━'*60}")
    try:
        from sc_playlist_manager import update_playlists
        update_playlists(youtube, episode_id, main_id, ep)
    except Exception as e:
        print(f"  ⚠️  プレイリスト処理でエラー（アップロード自体は成功）: {e}")

    # プレイリストID整合性検証＋自動修正
    # （手動削除・再作成やマシン間マージで playlist_id が実態とズレるのを防ぐ）
    print(f"{'━'*60}")
    print(f"  プレイリストID整合性検証")
    print(f"{'━'*60}")
    try:
        from sc_playlist_verify import verify_and_fix
        verify_and_fix(youtube, auto_fix=True, verbose=True)
    except Exception as e:
        print(f"  ⚠️  整合性検証でエラー（アップロード自体は成功）: {e}")

    # プレイリスト整合チェック＋自動補完
    # （非公開スキップ済みの動画を公開後に自動追加）
    print(f"{'━'*60}")
    print(f"  プレイリスト動画補完チェック")
    print(f"{'━'*60}")
    try:
        from sc_playlist_manager import _load_data, _save_data, _add_to_playlist
        pl_data = _load_data()
        added_count = 0
        for char_key, char_data in pl_data.items():
            pid = char_data.get("playlist_id")
            if not pid:
                continue
            try:
                # APIで実際のプレイリスト内動画IDを取得
                resp = youtube.playlistItems().list(
                    part="snippet", playlistId=pid, maxResults=50
                ).execute()
            except Exception:
                continue  # 整合性検証で修正できなかった不正なIDはスキップ
            actual_vids = {
                item["snippet"]["resourceId"]["videoId"]
                for item in resp.get("items", [])
            }
            # JSONに記録済みでAPIに未追加のものを補完
            for entry in char_data.get("episodes", []):
                vid = entry.get("video_id")
                if vid and vid not in actual_vids:
                    try:
                        _add_to_playlist(youtube, pid, vid)
                        print(f"  🔧 {char_key} / {entry['episode_id']}: プレイリストに補完追加")
                        added_count += 1
                    except Exception:
                        pass  # まだ非公開なら次回に持ち越し
        if added_count == 0:
            print(f"  ✅ 全プレイリスト整合済み（補完なし）")
        else:
            print(f"  ✅ {added_count}件を補完追加")
    except Exception as e:
        print(f"  ⚠️  整合チェックでエラー（アップロード自体は成功）: {e}")

    # index.html 再ビルド
    print(f"{'━'*60}")
    print(f"  サイト再ビルド")
    print(f"{'━'*60}")
    try:
        from sc_build_site import build as build_site
        build_site()
    except Exception as e:
        print(f"  ⚠️  サイトビルドでエラー（アップロード自体は成功）: {e}")


def fix_shorts_description(episode_id: str, shorts_id: str):
    """既存ShortsのURLを新フォーマットの説明文に更新する（本編IDは自動取得）"""
    import re

    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)

    with open(ep_json, encoding="utf-8") as f:
        ep = json.load(f)

    youtube = get_youtube_client()

    # 現在のShortsの説明文から本編IDを自動取得
    resp = youtube.videos().list(part="snippet", id=shorts_id).execute()
    if not resp.get("items"):
        print(f"❌ 動画が見つかりません: {shorts_id}")
        sys.exit(1)
    snippet = resp["items"][0]["snippet"]
    current_desc = snippet["description"]

    match = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", current_desc)
    if not match:
        print(f"❌ 現在の説明文から本編IDを取得できませんでした")
        print(current_desc[:200])
        sys.exit(1)
    main_id = match.group(1)
    print(f"  本編ID（自動取得）: {main_id}")

    hook_lines = ep.get("shorts_hook_lines", [])
    hook_text = "\n".join(hook_lines) if hook_lines else ep.get("episode_title", "")
    new_description = (
        f"{hook_text}\n\n"
        f"▶ Full episode: https://youtu.be/{main_id}\n\n"
        f"** Subscribe for new episodes every day:\n"
        f"https://www.youtube.com/@Samurai-Chronicles-JP"
    )

    print(f"\n{'━'*60}")
    print(f"  Shorts説明文を更新: {shorts_id}")
    print(f"{'━'*60}")
    print(new_description)
    print(f"{'━'*60}\n")

    snippet["description"] = new_description
    youtube.videos().update(
        part="snippet",
        body={"id": shorts_id, "snippet": snippet},
    ).execute()

    print(f"  ✓ 説明文を更新しました: https://youtube.com/shorts/{shorts_id}")


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles YouTube アップロード")
    parser.add_argument("--episode", required=False, help="エピソードID（例: ep001）")
    parser.add_argument("--publish-at", metavar="DATETIME",
                        help="予約公開日時（JST）例: '2026-06-01 20:00' / 省略時は翌 03:00 JST に自動予約")
    parser.add_argument("--now", action="store_true",
                        help="即時公開（03:00 JST 自動予約をスキップ）")
    parser.add_argument("--fix-shorts", metavar="SHORTS_ID", help="既存ShortsのIDを指定して説明文を修正（本編IDは自動取得）")
    args = parser.parse_args()

    if args.fix_shorts:
        if not args.episode:
            parser.error("--fix-shorts には --episode も必要です")
        fix_shorts_description(args.episode, args.fix_shorts)
    elif args.episode:
        run(args.episode, publish_at=args.publish_at, publish_now=args.now)
    else:
        parser.error("--episode または --fix-shorts を指定してください")


if __name__ == "__main__":
    cli()
