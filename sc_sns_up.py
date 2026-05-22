"""
sc_sns_up.py — Samurai Chronicles YouTube アップロード

使い方:
  python3 sc_sns_up.py --episode ep001

アップロード内容:
  1. 本編動画（タイトル・説明文・タグ・字幕）
  2. Shorts動画（タイトル末尾に #Shorts を付加）

認証: ~/.claude/secrets/yt_client_secrets.json（Lamps Whisper と共用）
"""

import argparse
import json
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

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
            creds = flow.run_local_server(port=0, prompt="select_account consent")
        YT_TOKEN.parent.mkdir(parents=True, exist_ok=True)
        YT_TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path: Path, title: str, description: str,
                 tags: list) -> str:
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
            "status": {"privacyStatus": "public"},
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%", end="\r")
    video_id = response["id"]
    print(f"  ✓ 完了: https://youtu.be/{video_id}")
    return video_id


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


def run(episode_id: str):
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

    title = ep["youtube_title"]
    description = ep["youtube_description"]
    tags = ep.get("youtube_tags", [])

    print(f"\n{'━'*60}")
    print(f"  {episode_id} — YouTube アップロード")
    print(f"{'━'*60}\n")

    for path, label in [(main_video, "本編"), (shorts_video, "Shorts")]:
        if not path.exists():
            print(f"❌ {label}動画が見つかりません: {path}")
            sys.exit(1)

    youtube = get_youtube_client()

    # 本編
    print("【本編】")
    main_id = upload_video(youtube, main_video, title, description, tags)
    if srt_file.exists():
        upload_caption(youtube, main_id, srt_file)
    else:
        print(f"  ⚠️  字幕ファイルなし（スキップ）")

    time.sleep(2)

    # Shorts
    print("\n【Shorts】")
    shorts_id = upload_video(youtube, shorts_video,
                             f"{title} #Shorts", description, tags + ["shorts"])

    print(f"\n{'━'*60}")
    print(f"  ✓ アップロード完了（公開）")
    print(f"  本編:   https://youtu.be/{main_id}")
    print(f"  Shorts: https://youtu.be/{shorts_id}")
    print(f"{'━'*60}\n")


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles YouTube アップロード")
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep001）")
    args = parser.parse_args()
    run(args.episode)


if __name__ == "__main__":
    cli()
