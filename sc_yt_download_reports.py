#!/usr/bin/env python3
"""
sc_yt_download_reports.py — YouTube Reporting API の全レポートを一括ダウンロード

使い方:
  python3 sc_yt_download_reports.py            # 全ジョブの未取得レポートを差分DL
  python3 sc_yt_download_reports.py --force    # 既存ファイルも上書き再DL

保存先: analytics/raw/{job_name}/{date}.csv
  例: analytics/raw/channel_reach_basic_a1/2026-06-24.csv
"""

import argparse
import gzip
import sys
from pathlib import Path

import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SECRETS_DIR = Path.home() / ".claude" / "secrets"
YT_TOKEN_REPORTING = SECRETS_DIR / "yt_token_sc_reporting.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

OUTPUT_DIR = Path(__file__).parent / "analytics" / "raw"

JOBS = {
    "093d614d-0cbd-4cbb-a798-4a60b4cdae8c": "channel_reach_basic_a1",
    "5d116273-ef92-4e17-900e-7003146c743b": "channel_combined_a3",
    "949a1502-3393-4532-a752-3ecd9278d529": "channel_demographics_a1",
}


def get_creds():
    if not YT_TOKEN_REPORTING.exists():
        print(f"❌ トークンが見つかりません: {YT_TOKEN_REPORTING}")
        print("   先に `python3 sc_yt_reporting_auth.py` を実行してください。")
        sys.exit(1)
    creds = Credentials.from_authorized_user_file(str(YT_TOKEN_REPORTING), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            YT_TOKEN_REPORTING.write_text(creds.to_json())
        else:
            print("❌ トークンが無効です。sc_yt_reporting_auth.py で再認証してください。")
            sys.exit(1)
    return creds


def download_all(force: bool):
    creds = get_creds()
    yt = build("youtubereporting", "v1", credentials=creds)
    authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http())

    total_new = 0
    total_skip = 0

    for job_id, job_name in JOBS.items():
        out_dir = OUTPUT_DIR / job_name
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n━━━ {job_name} ━━━")
        resp = yt.jobs().reports().list(jobId=job_id).execute()
        reports = resp.get("reports", [])

        for rep in reports:
            # 期間の開始日をファイル名に使う（UTC→日付文字列）
            date_str = rep["startTime"][:10]  # "2026-06-24T07:00:00Z" → "2026-06-24"
            out_path = out_dir / f"{date_str}.csv"

            if out_path.exists() and not force:
                total_skip += 1
                continue

            url = rep["downloadUrl"]
            http_resp, content = authed_http.request(url)
            if http_resp.status != 200:
                print(f"  ❌ {date_str}: ダウンロード失敗 (status={http_resp.status})")
                continue

            # レスポンスが gzip の場合は展開
            content_encoding = http_resp.get("content-encoding", "")
            if content_encoding == "gzip" or content[:2] == b"\x1f\x8b":
                content = gzip.decompress(content)

            out_path.write_bytes(content)
            print(f"  ✓ {date_str}.csv")
            total_new += 1

    print(f"\n完了: {total_new}件ダウンロード、{total_skip}件スキップ（既存）")


def main():
    parser = argparse.ArgumentParser(description="YouTube Reporting API 全レポート一括DL")
    parser.add_argument("--force", action="store_true", help="既存ファイルも上書き再DL")
    args = parser.parse_args()
    download_all(args.force)


if __name__ == "__main__":
    main()
