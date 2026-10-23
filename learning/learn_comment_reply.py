#!/usr/bin/env python3
"""学習版チャンネル（英語で聴く日本史）の未返信コメントを取得／返信投稿する（/sc-upload STEP 3.7）。
sc_comment_reply.py の学習版チャンネル用。認証・チャンネル・記録ファイルだけが違う。

  python3 learning/learn_comment_reply.py list            # 未返信コメントをJSONで出力（投稿しない）
  python3 learning/learn_comment_reply.py post FILE.json  # {"スレッドID": "返信文", ...} を投稿

返信文は Claude が内容に合わせて**日本語で**書く。スクリプトは取得と投稿のみ。
返信済みスレッドIDは data/learn_comment_replies.json に記録（二重返信防止）。
自分のコメントや、すでに自分の返信があるスレッドは対象外。
"""
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CHANNEL_ID = "UCWOFhTRNmbVeVWgwF9DfoNA"   # 英語で聴く日本史（@eigo-de-nihonshi）
TOKEN = Path.home() / ".claude/secrets/yt_token_learn.json"
CLIENT_SECRETS = Path.home() / ".claude/secrets/yt_client_secrets_learn.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
LOG = Path(__file__).parent.parent / "data/learn_comment_replies.json"   # SC のリポジトリの data/ に置く


def youtube():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError:  # 失効（過去に繰り返し発生）→ブラウザで再認証
            from google_auth_oauthlib.flow import InstalledAppFlow
            print("  トークン失効: ブラウザで「英語で聴く日本史」のチャンネルを選んで許可してください")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
            creds = flow.run_local_server(port=8082, prompt="select_account consent")
        TOKEN.write_text(creds.to_json())
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="id", mine=True).execute().get("items", [])
    if not ch or ch[0]["id"] != CHANNEL_ID:
        sys.exit("認証チャンネルが学習版（英語で聴く日本史）ではありません。中止します。")
    return yt


def mine(sn):
    return sn.get("authorChannelId", {}).get("value") == CHANNEL_ID


def load_done():
    return set(json.loads(LOG.read_text())["replied"]) if LOG.exists() else set()


def unreplied(yt, max_pages=5):
    done, token, out = load_done(), None, []
    titles = {}
    for _ in range(max_pages):
        r = yt.commentThreads().list(
            part="snippet,replies", allThreadsRelatedToChannelId=CHANNEL_ID,
            maxResults=100, order="time", textFormat="plainText", pageToken=token).execute()
        for th in r.get("items", []):
            sn = th["snippet"]["topLevelComment"]["snippet"]
            replies = th.get("replies", {}).get("comments", [])
            if (mine(sn) or th["id"] in done
                    or th["snippet"]["totalReplyCount"] > len(replies)
                    or any(mine(x["snippet"]) for x in replies)):
                continue
            vid = sn["videoId"]
            if vid not in titles:
                v = yt.videos().list(part="snippet", id=vid).execute().get("items", [])
                titles[vid] = v[0]["snippet"]["title"] if v else ""
            out.append({"thread_id": th["id"], "video_id": vid, "video_title": titles[vid],
                        "author": sn["authorDisplayName"], "text": sn["textDisplay"],
                        "likes": sn.get("likeCount", 0), "published": sn["publishedAt"]})
        token = r.get("nextPageToken")
        if not token:
            break
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "post"):
        sys.exit(__doc__)
    yt = youtube()
    if sys.argv[1] == "list":
        print(json.dumps(unreplied(yt), ensure_ascii=False, indent=1))
        return
    replies = json.loads(Path(sys.argv[2]).read_text())
    done = load_done()
    for tid, text in replies.items():
        if tid in done or not text.strip():
            continue
        try:
            yt.comments().insert(part="snippet", body={
                "snippet": {"parentId": tid, "textOriginal": text}}).execute()
            done.add(tid)
            print(f"  ✓ {tid}: {text}")
        except Exception as e:
            print(f"  ⚠ {tid}: 失敗 {e}")
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps({"replied": sorted(done)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
