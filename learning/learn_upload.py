"""学習版（英語で聴く日本史）を、学習版チャンネルに YouTube Data API でアップロードする。

アップロードするもの: 本編（mp4）＋サムネイル、ショート（mp4）。説明文にはチャプターと、英語版へのリンクを入れる。
公開の既定は**非公開**（確認用）。`--publish-at` で予約公開、`--now` で即時公開。
**ユーザーが動画を確認して OK を出すまで、実行しない**（/sc-learn の決まり）。

認証（学習版専用の Google Cloud プロジェクト。手順は YOUTUBE_SETUP.md）:
  ~/.claude/secrets/yt_client_secrets_learn.json   OAuth クライアント ID（デスクトップアプリ）
  ~/.claude/secrets/yt_token_learn.json            初回の認証で自動作成
毎回、認証したチャンネルが学習版チャンネル（CHANNEL_ID）か確認し、違えば止まる（誤チャンネルへのアップロード防止）。

使い方:
  python3 learn_upload.py ep106 --dry-run                          タイトル・説明・チャプターを表示（通信しない）
  python3 learn_upload.py --auth-only                              認証だけ行い、チャンネルを確認する
  python3 learn_upload.py ep106                                    非公開でアップロード（確認用）
  python3 learn_upload.py ep106 --publish-at "2026-10-28 20:00"    予約公開（JST）
  python3 learn_upload.py ep106 --now                              即時公開
  python3 learn_upload.py ep106 --schedule-existing                アップロード済み（非公開）の2本を、SC 本編の公開日時に公開予定にする
                                                                   （SC がすでに公開済みなら、その場で公開）

記録: アップロードした動画の ID は learning/uploads/ep{NNN}.json に残す（learn_targets.py と共通）。
公開（--now / --publish-at）は、learn_targets.py --approve で「公開 OK」が記録された回だけ。
"""
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
SC_DIR = BASE_DIR.parent
sys.path.insert(0, str(SC_DIR))

DRIVE = (Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles")
CHANNEL_ID = "UCWOFhTRNmbVeVWgwF9DfoNA"   # 英語で聴く日本史（@eigo-de-nihonshi）
SECRETS_DIR = Path.home() / ".claude" / "secrets"
CLIENT_SECRETS = SECRETS_DIR / "yt_client_secrets_learn.json"
TOKEN = SECRETS_DIR / "yt_token_learn.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
AUTH_PORT = 8082          # 本編（SC）の認証は 8081
CATEGORY_EDUCATION = "27"
SYNTHETIC = True          # 合成・改変コンテンツの申告（containsSyntheticMedia）。本編（sc_sns_up.py）と同じ。AI 音声・生成画像を使うため。公開前に最新の規約で再確認する
THUMB_LIMIT = 2 * 1024 * 1024   # YouTube のサムネイルの上限（2MB）
BASE_TAGS = ["英語リスニング", "英語耳", "日本史", "歴史", "英語学習", "リスニング", "英語で日本史", "Samurai Chronicles"]


def mmss(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}" if sec < 3600 else f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}"


def chapters(tl: dict) -> list:
    """タイムラインから、YouTube のチャプター（先頭は 00:00、各10秒以上、3つ以上）を作る。"""
    ev = tl["events"]
    out = [(0, "導入")]
    for e in sorted((x for x in ev if x["kind"] == "cue"), key=lambda x: x["start"]):
        body = e["text"].split("。", 1)[1] if "。" in e["text"] else ""
        first = body.split("。")[0].strip() if body else ""   # 「シーンN。」の次の1文（見どころ）。途中で切らない
        out.append((e["start"], f"シーン{e['scene']}" + (f"：{first}" if first else "")))
    out.append((next(x for x in ev if x["kind"] == "to_full")["start"], "通しで聴く（英語のみ）"))
    out.append((next(x for x in ev if x["kind"] == "closing")["start"], "締め"))
    return out


def build_metadata(ep_id: str) -> dict:
    lesson = json.loads((BASE_DIR / "lessons" / f"{ep_id}.json").read_text(encoding="utf-8"))
    tl = json.loads((BASE_DIR / "build" / ep_id / "timeline.json").read_text(encoding="utf-8"))
    ep = json.loads((SC_DIR / "episodes" / f"{ep_id}.json").read_text(encoding="utf-8"))
    title_ja = lesson["title_ja"]
    minutes = round(tl["total"] / 60)
    title = f"【英語で聴く日本史】{title_ja}｜日本史を聴くだけで英語耳に"
    ch = "\n".join(f"{mmss(t)} {name}" for t, name in chapters(tl))
    en_url = ep.get("youtube_url", "")
    desc = (
        "日本史を聴くだけで、英語耳に。\n"
        f"{title_ja}を、英語のナレーションで聴いて、1文ずつ日本語の訳とワンポイント解説で確かめていく、約{minutes}分の英語リスニング教材です。\n\n"
        "▼ この動画の流れ\n"
        "・シーンごとに、日本語で見どころを説明\n"
        "・1文ずつ「合図の音 → 日本語の訳 → 英語」で、聞き取れないまま進まない\n"
        "・各シーンの最後に、使える英語表現のワンポイント\n"
        "・最後に、英語だけの通し聴き\n\n"
        f"▼ チャプター\n{ch}\n\n"
        + (f"▼ 元の英語版（歴史ドキュメンタリー）\n{en_url}\n\n" if en_url else "")
        + "語り手: Tokio Kamiya（過去の日本から現地報告を送る時空リポーター）\n"
        "チャンネル: 英語で聴く日本史（英語版: Samurai Chronicles）"
    )
    person = title_ja.split("—")[0].strip().split()[0]
    tags = BASE_TAGS + ([person] if person else [])
    short = lesson.get("promo", {}).get("short", {})
    short_title = f"{short.get('quiz_title', title_ja)}、英語で言える？ #Shorts"
    return {"title": title, "description": desc, "tags": tags, "minutes": minutes,
            "short_title": short_title, "title_ja": title_ja}


def get_youtube_client():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS.exists():
                print(f"❌ 認証ファイルがありません: {CLIENT_SECRETS}\n   手順書 YOUTUBE_SETUP.md の「4. Google Cloud プロジェクトと API の準備」を先に行ってください")
                sys.exit(1)
            print("  ブラウザが開きます。⚠️ アカウントの選択では、学習版チャンネル（英語で聴く日本史）を選んでください")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
            creds = flow.run_local_server(port=AUTH_PORT, prompt="select_account consent")
        TOKEN.parent.mkdir(parents=True, exist_ok=True)
        TOKEN.write_text(creds.to_json())
    youtube = build("youtube", "v3", credentials=creds)
    items = youtube.channels().list(part="snippet", mine=True).execute().get("items", [])
    if not items:
        print("❌ チャンネル情報を取得できませんでした")
        sys.exit(1)
    cid, name = items[0]["id"], items[0]["snippet"]["title"]
    print(f"  認証チャンネル: {name} ({cid})")
    if cid != CHANNEL_ID:
        print("  ❌ 学習版チャンネルではありません！ 認証をやり直してください（トークンを削除します）")
        TOKEN.unlink(missing_ok=True)
        sys.exit(1)
    return youtube


def upload_video(youtube, path: Path, title: str, description: str, tags: list, publish_at=None, now=False) -> str:
    from googleapiclient.http import MediaFileUpload
    from sc_sns_up import parse_publish_at   # 予約日時（JST）→ UTC の変換は本編と同じ
    status = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": SYNTHETIC}
    if publish_at:
        status.update({"privacyStatus": "private", "publishAt": parse_publish_at(publish_at)})
        mode = f"予約公開 {publish_at} JST"
    elif now:
        status["privacyStatus"] = "public"
        mode = "即時公開"
    else:
        status["privacyStatus"] = "private"
        mode = "非公開（確認用）"
    print(f"  アップロード中（{mode}）: {path.name} ...")
    req = youtube.videos().insert(
        part="snippet,status",
        body={"snippet": {"title": title, "description": description, "tags": tags, "categoryId": CATEGORY_EDUCATION,
                          "defaultLanguage": "ja", "defaultAudioLanguage": "ja"},
              "status": status},
        media_body=MediaFileUpload(str(path), chunksize=-1, resumable=True),
    )
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            print(f"  {int(st.progress() * 100)}%", end="\r")
    print(f"  ✓ 完了: https://youtu.be/{resp['id']}")
    return resp["id"]


def schedule_existing(youtube, ep_id: str):
    """アップロード済みの本編・ショートを、SC 本編の公開日時（scheduled_at）に公開予定にする。過ぎていれば即公開。"""
    from datetime import datetime, timedelta, timezone
    from learn_targets import load_rec
    from sc_sns_up import parse_publish_at
    rec = load_rec(ep_id)
    if not rec.get("approved"):
        sys.exit(f"❌ 公開の OK が記録されていません。`python3 learn_targets.py --approve {ep_id}` のあとに実行してください")
    if not (rec.get("main_id") and rec.get("short_id")):
        sys.exit(f"❌ {ep_id}: アップロード済みの記録がありません")
    sc = json.loads((SC_DIR / "episodes" / f"{ep_id}.json").read_text(encoding="utf-8"))
    sched = sc.get("scheduled_at")
    if not sched:
        sys.exit(f"❌ {ep_id}: SC 本編の scheduled_at がありません")
    jst = timezone(timedelta(hours=9))
    future = datetime.strptime(sched, "%Y-%m-%d %H:%M").replace(tzinfo=jst) > datetime.now(jst)
    status = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": SYNTHETIC}
    if future:
        status.update({"privacyStatus": "private", "publishAt": parse_publish_at(sched)})
        mode = f"予約公開 {sched} JST"
    else:
        status["privacyStatus"] = "public"
        mode = f"即時公開（SC の公開時刻 {sched} を過ぎている）"
    for label, vid in (("本編", rec["main_id"]), ("ショート", rec["short_id"])):
        youtube.videos().update(part="status", body={"id": vid, "status": status}).execute()
        print(f"  ✓ {label} https://youtu.be/{vid} → {mode}")
    rec.update({"publish_at": sched, "now": not future})
    from learn_targets import save_rec
    save_rec(ep_id, rec)


def upload_thumbnail(youtube, video_id: str, path: Path):
    from googleapiclient.http import MediaFileUpload
    print(f"  サムネイル: {path.name} ...")
    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(path), mimetype="image/png")).execute()
    print("  ✓ サムネイル完了")


def main():
    ap = argparse.ArgumentParser(description="学習版を学習版チャンネルにアップロードする")
    ap.add_argument("episode", nargs="?", help="例: ep106")
    ap.add_argument("--publish-at", help='予約公開の日時（JST）。例: "2026-10-28 20:00"')
    ap.add_argument("--now", action="store_true", help="即時公開")
    ap.add_argument("--schedule-existing", action="store_true", help="アップロード済みの2本を、SC 本編の公開日時に公開予定にする")
    ap.add_argument("--dry-run", action="store_true", help="通信せず、内容と素材の確認だけ")
    ap.add_argument("--auth-only", action="store_true", help="認証とチャンネルの確認だけ")
    a = ap.parse_args()

    if a.auth_only:
        get_youtube_client()
        print("✅ 認証できました")
        return
    if not a.episode:
        ap.error("エピソード番号（例: ep106）が必要です")
    ep_id = a.episode
    if a.schedule_existing:
        schedule_existing(get_youtube_client(), ep_id)
        return
    meta = build_metadata(ep_id)
    out_dir = DRIVE / ep_id / "learning"
    main_mp4 = out_dir / f"{ep_id} {meta['title_ja']}.mp4"
    short_mp4 = out_dir / f"{ep_id}_learning_short.mp4"
    thumb = out_dir / f"{ep_id}_learning_thumbnail.png"
    files = {"本編": main_mp4, "ショート": short_mp4, "サムネイル": thumb}
    missing = [f"{k}: {v}" for k, v in files.items() if not v.exists()]

    print(f"\n=== {ep_id} ===\nタイトル: {meta['title']}（{len(meta['title'])}字）\nタグ: {', '.join(meta['tags'])}\n\n{meta['description']}\n")
    print(f"ショートのタイトル: {meta['short_title']}")
    for k, v in files.items():
        print(f"  {k}: {'あり' if v.exists() else '❌ なし'}  {v.stat().st_size // 1024 // 1024 if v.exists() else 0}MB")
    if thumb.exists() and thumb.stat().st_size > THUMB_LIMIT:
        print(f"  ❌ サムネイルが2MBを超えています（{thumb.stat().st_size // 1024}KB）")
        sys.exit(1)
    if missing:
        print("\n❌ 素材がありません:\n  " + "\n  ".join(missing))
        sys.exit(1)
    if a.dry_run:
        print("\n（dry-run: アップロードはしていません）")
        return

    from learn_targets import load_rec, save_rec, rec_path
    rec = load_rec(ep_id)
    if (a.now or a.publish_at) and not rec.get("approved"):
        print(f"❌ 公開の OK が記録されていません。ユーザーが確認して OK を出したあと、`python3 learn_targets.py --approve {ep_id}` で記録してください"
              "（非公開でのアップロードは、OK がなくてもできます）")
        sys.exit(1)
    youtube = get_youtube_client()
    if rec.get("short_id"):
        print(f"❌ すでにアップロード済みです: https://youtu.be/{rec['main_id']}（{rec_path(ep_id)}）。やり直す場合は、YouTube Studio で削除し、記録ファイルを消してください")
        sys.exit(1)
    if rec.get("main_id"):
        main_id = rec["main_id"]
        print(f"  本編はアップロード済み（https://youtu.be/{main_id}）。続きから進めます")
    else:
        main_id = upload_video(youtube, main_mp4, meta["title"], meta["description"], meta["tags"], a.publish_at, a.now)
        rec["main_id"] = main_id
        save_rec(ep_id, rec)
    if not rec.get("thumb_set"):
        upload_thumbnail(youtube, main_id, thumb)   # 電話番号の確認前は 403 になる（本編の記録は残る）
        rec["thumb_set"] = True
        save_rec(ep_id, rec)
    short_desc = (f"日本史を聴くだけで、英語耳に。\n▶ 本編（約{meta['minutes']}分）: https://youtu.be/{main_id}\n\n"
                  f"{meta['title_ja']}を、英語で聴いて、日本語の訳と解説で確かめる英語リスニング教材です。")
    short_id = upload_video(youtube, short_mp4, meta["short_title"], short_desc, meta["tags"] + ["Shorts"], a.publish_at, a.now)
    rec.update({"short_id": short_id, "publish_at": a.publish_at, "now": a.now, "related_video_set": False})
    save_rec(ep_id, rec)
    print(f"\n✅ 完了\n  本編: https://youtu.be/{main_id}\n  ショート: https://youtu.be/{short_id}\n  記録: {rec_path(ep_id)}"
          "\n  次: ショートの関連動画を設定する（/sc-upload STEP 3.7。API では設定できないので Chrome で行う）")


if __name__ == "__main__":
    main()
