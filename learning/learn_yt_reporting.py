#!/usr/bin/env python3
"""学習版チャンネル（英語で聴く日本史）の YouTube アナリティクスのデータ取得（Reporting API）。
SC の sc_yt_reporting_auth.py / sc_yt_reporting_job.py / sc_yt_download_reports.py と同じ仕組みを、1つにまとめたもの。

Reporting API は、ジョブを作った時点から日次のレポートを溜める。**ジョブを作るのが遅れた分のデータは戻らない**ので、
チャンネルを公開したら早めに `setup` を実行すること。

前提（Google Cloud のプロジェクト sc-learning-512503。手順は YOUTUBE_SETUP.md の「アナリティクス」）:
  ・「YouTube Reporting API」と「YouTube Analytics API」を有効にしてある
  ・認証用のクライアント ~/.claude/secrets/yt_client_secrets_learn.json（アップロードと共通）

使い方:
  python3 learn_yt_reporting.py auth       分析用の権限（yt-analytics.readonly）を追加して認証する（ブラウザで許可）
  python3 learn_yt_reporting.py setup      レポートのジョブを登録する（登録済みなら何もしない）
  python3 learn_yt_reporting.py download   未取得のレポートを Drive に保存する（差分のみ。--force で上書き）
  python3 learn_yt_reporting.py status     ジョブと取得済みレポートの数を表示する

保存先: Google Drive samurai-chronicles/analytics_learning/raw/{ジョブ名}/{日付}.csv
トークン: ~/.claude/secrets/yt_token_learn_reporting.json（アップロード用の yt_token_learn.json とは別ファイル）
"""
import argparse
import gzip
import sys
from pathlib import Path

CHANNEL_ID = "UCWOFhTRNmbVeVWgwF9DfoNA"   # 英語で聴く日本史（@eigo-de-nihonshi）
SECRETS_DIR = Path.home() / ".claude" / "secrets"
CLIENT_SECRETS = SECRETS_DIR / "yt_client_secrets_learn.json"
TOKEN = SECRETS_DIR / "yt_token_learn_reporting.json"
AUTH_PORT = 8082
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
DRIVE = Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles"
RAW_DIR = DRIVE / "analytics_learning" / "raw"

# SC と同じ3種類（reach=インプレッション・CTR、combined=視聴・視聴時間・登録・流入経路、demographics=年齢・性別）
JOB_TYPES = {
    "channel_reach_basic_a1": "learn-reach",
    "channel_combined_a3": "learn-combined",
    "channel_demographics_a1": "learn-demographics",
}


def creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not TOKEN.exists():
        sys.exit(f"❌ トークンがありません: {TOKEN}\n   先に `python3 learn_yt_reporting.py auth` を実行してください。")
    c = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not c.valid:
        if c.expired and c.refresh_token:
            c.refresh(Request())
            TOKEN.write_text(c.to_json())
        else:
            sys.exit("❌ トークンが無効です。`python3 learn_yt_reporting.py auth` で再認証してください。")
    return c


def cmd_auth(_):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    if not CLIENT_SECRETS.exists():
        sys.exit(f"❌ 認証ファイルがありません: {CLIENT_SECRETS}")
    c = None
    if TOKEN.exists():
        try:
            c = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except Exception:  # noqa: BLE001
            c = None
    if c and c.expired and c.refresh_token:
        try:
            c.refresh(Request())
        except Exception:  # noqa: BLE001
            c = None
    if not (c and c.valid):
        print("ブラウザが開きます。⚠️ アカウントの選択では、学習版チャンネル（英語で聴く日本史）を選んでください")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
        c = flow.run_local_server(port=AUTH_PORT, prompt="select_account consent", access_type="offline")
        TOKEN.write_text(c.to_json())
        TOKEN.chmod(0o600)
    items = build("youtube", "v3", credentials=c).channels().list(part="snippet", mine=True).execute().get("items", [])
    if not items or items[0]["id"] != CHANNEL_ID:
        TOKEN.unlink(missing_ok=True)
        sys.exit(f"❌ 学習版チャンネルではありません（{items[0]['snippet']['title'] if items else '不明'}）。もう一度、学習版を選んで認証してください")
    print(f"✅ 認証できました: {items[0]['snippet']['title']} ({CHANNEL_ID})")


def reporting():
    from googleapiclient.discovery import build
    return build("youtubereporting", "v1", credentials=creds())


def existing_jobs(yt) -> dict:
    return {j["reportTypeId"]: j for j in yt.jobs().list().execute().get("jobs", [])}


def cmd_setup(_):
    yt = reporting()
    have = existing_jobs(yt)
    for rtype, name in JOB_TYPES.items():
        if rtype in have:
            print(f"  ・{rtype}: 登録済み（{have[rtype]['id']}）")
            continue
        job = yt.jobs().create(body={"reportTypeId": rtype, "name": name}).execute()
        print(f"  ✓ {rtype}: ジョブを登録しました（{job['id']}）。レポートは、約1日後から毎日生成されます")


def cmd_download(a):
    import google_auth_httplib2
    import httplib2
    c = creds()
    yt = reporting()
    http = google_auth_httplib2.AuthorizedHttp(c, http=httplib2.Http())
    if not DRIVE.exists():
        sys.exit(f"❌ Google Drive の同期フォルダがありません: {DRIVE}")
    new = skip = 0
    for rtype, job in existing_jobs(yt).items():
        if rtype not in JOB_TYPES:
            continue
        out_dir = RAW_DIR / JOB_TYPES[rtype]
        out_dir.mkdir(parents=True, exist_ok=True)
        latest = {}
        for rep in yt.jobs().reports().list(jobId=job["id"]).execute().get("reports", []):
            d = rep["startTime"][:10]
            if d not in latest or rep.get("createTime", "") > latest[d].get("createTime", ""):
                latest[d] = rep
        print(f"━━━ {JOB_TYPES[rtype]}（レポート {len(latest)} 日分）")
        for d, rep in sorted(latest.items()):
            path = out_dir / f"{d}.csv"
            if path.exists() and not a.force:
                skip += 1
                continue
            resp, content = http.request(rep["downloadUrl"])
            if resp.status != 200:
                print(f"  ❌ {d}: ダウンロード失敗（{resp.status}）")
                continue
            if content[:2] == b"\x1f\x8b":
                content = gzip.decompress(content)
            path.write_bytes(content)
            new += 1
            print(f"  ✓ {d}.csv")
    print(f"\n完了: {new}件ダウンロード、{skip}件スキップ（既存）")


def cmd_status(_):
    yt = reporting()
    have = existing_jobs(yt)
    for rtype, name in JOB_TYPES.items():
        j = have.get(rtype)
        n = len(list((RAW_DIR / name).glob("*.csv"))) if (RAW_DIR / name).exists() else 0
        print(f"  {name:20s} {'登録済み ' + j['id'] if j else '未登録'}  取得済み {n} 日分")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth")
    sub.add_parser("setup")
    d = sub.add_parser("download")
    d.add_argument("--force", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()
    {"auth": cmd_auth, "setup": cmd_setup, "download": cmd_download, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
