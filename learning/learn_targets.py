"""学習版の「公開してよい回」と「関連動画の設定が必要な回」を洗い出す／記録する（/sc-upload の STEP 3.7 で使う）。

SC の本編が公開された回と**同じ EP 番号**の学習版を、そのタイミングでアップロード（即時公開）し、
ショートの関連動画を設定し、コメントに返信する（2026-10-23 ユーザー決定）。
sc_related_targets.py と同じ作り。状態は learning/uploads/ep{NNN}.json に持つ:

  approved           ユーザーが「公開してよい」と OK を出した（--approve で記録）。OK のない回は公開しない
  main_id/short_id   アップロード済みの動画 ID（learn_upload.py が記録）
  related_video_set  ショートの関連動画を設定済み（--mark-related で記録）

使い方:
  python3 learn_targets.py                      対象を一覧表示（アップロード対象・関連動画の設定対象）
  python3 learn_targets.py --json               同じ内容を JSON で表示
  python3 learn_targets.py --approve ep106      公開 OK を記録（ユーザーが動画・サムネイル・ショートを確認して OK を出したあと）
  python3 learn_targets.py --mark-related ep106 関連動画の設定完了を記録（画面で確かめたあと）
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR.parent))
from sc_related_targets import is_public, load_all, video_id   # noqa: E402  SC の公開判定（scheduled_at を過ぎたか）を共用

UPLOADS = BASE_DIR / "uploads"
JST = timezone(timedelta(hours=9))


def rec_path(ep_id: str) -> Path:
    return UPLOADS / f"{ep_id}.json"


def load_rec(ep_id: str) -> dict:
    p = rec_path(ep_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_rec(ep_id: str, rec: dict):
    UPLOADS.mkdir(exist_ok=True)
    rec_path(ep_id).write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def title_ja(ep_id: str) -> str:
    p = BASE_DIR / "lessons" / f"{ep_id}.json"
    return json.loads(p.read_text(encoding="utf-8"))["title_ja"] if p.exists() else ""


def targets(now: datetime) -> dict:
    """upload: 学習版の公開 OK があり、まだアップロードしていない回（公開日時は SC 本編に合わせる）
       related: アップロード済み（本編・ショートとも公開）で、関連動画が未設定の回
       waiting: 学習版はあるが、SC がまだ公開されていない／OK が出ていない回（参考）"""
    upload, related, waiting = [], [], []
    for _, ep in load_all():
        eid = ep["episode_id"]
        if not (BASE_DIR / "lessons" / f"{eid}.json").exists():
            continue
        rec = load_rec(eid)
        published = is_public(ep, now)
        if rec.get("main_id") and rec.get("short_id"):
            if not rec.get("related_video_set") and published:
                related.append({"episode_id": eid, "main_id": rec["main_id"], "shorts_id": rec["short_id"],
                                "search": title_ja(eid)})
            continue
        if rec.get("approved"):
            upload.append({"episode_id": eid, "title_ja": title_ja(eid), "sc_url": ep.get("youtube_url", ""),
                           "scheduled_at": ep.get("scheduled_at", "")})
        else:
            why = []
            if not rec.get("approved"):
                why.append("公開 OK 未記録")
            waiting.append({"episode_id": eid, "reason": "、".join(why)})
    return {"upload": upload, "related": related, "waiting": waiting}


def main():
    ap = argparse.ArgumentParser(description="学習版の公開・関連動画の対象を管理する")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--approve", nargs="+", metavar="EPISODE")
    ap.add_argument("--mark-related", nargs="+", metavar="EPISODE")
    a = ap.parse_args()
    if a.approve:
        for eid in a.approve:
            if not (BASE_DIR / "lessons" / f"{eid}.json").exists():
                sys.exit(f"学習版の台本がありません: lessons/{eid}.json")
            rec = load_rec(eid)
            rec["approved"] = True
            save_rec(eid, rec)
            print(f"  ✓ {eid}: 公開 OK を記録しました（次の /sc-upload で、SC 本編と同じ日時に公開予定でアップロードされます）")
        return
    if a.mark_related:
        for eid in a.mark_related:
            rec = load_rec(eid)
            if not rec.get("short_id"):
                sys.exit(f"{eid}: アップロード済みの記録がありません")
            rec["related_video_set"] = True
            save_rec(eid, rec)
            print(f"  ✓ {eid}: related_video_set = true")
        return
    t = targets(datetime.now(JST))
    if a.json:
        print(json.dumps(t, ensure_ascii=False, indent=2))
        return
    print(f"アップロード対象（公開 OK あり・未アップロード）: {len(t['upload'])}件")
    for r in t["upload"]:
        print(f"  {r['episode_id']}  {r['title_ja']}")
    print(f"関連動画の設定対象: {len(t['related'])}件")
    for r in t["related"]:
        print(f"  {r['episode_id']}  shorts={r['shorts_id']}  本編={r['main_id']}  検索語「{r['search']}」")
    if t["waiting"]:
        print("待ち（参考）:")
        for r in t["waiting"]:
            print(f"  {r['episode_id']}  {r['reason']}")


if __name__ == "__main__":
    main()
