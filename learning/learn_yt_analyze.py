#!/usr/bin/env python3
"""学習版チャンネル（英語で聴く日本史）の YouTube アナリティクスの集計。/learn-analytics から使う。

データ: ・Analytics API（その場で集計。視聴・視聴時間・維持率の曲線・流入経路・国・端末・登録者）
        ・Reporting API のレポート（Drive の analytics_learning/raw/。インプレッションと CTR は、こちらにしかない）
対象: learning/uploads/ep*.json に記録した、学習版の本編とショート。
注意: YouTube のデータは 2〜3 日遅れる。公開から日が浅い回は、数値が空・小さいことがある。

使い方:
  python3 learn_yt_analyze.py                回ごとの一覧（本編）と、ショート、維持率、流入、国
  python3 learn_yt_analyze.py --retention    維持率の曲線だけ（動画の長さの何割の所で、視聴者が何割残っているか）
  python3 learn_yt_analyze.py --json         集計結果を JSON で出す（解釈を Opus に渡すとき用）
"""
import argparse
import csv
import glob
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
from learn_yt_reporting import CHANNEL_ID, RAW_DIR, creds   # noqa: E402

JST = timezone(timedelta(hours=9))
RETENTION_POINTS = [0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98]   # 動画の長さの何割の所か


def episodes() -> list:
    out = []
    for p in sorted(glob.glob(str(BASE_DIR / "uploads" / "ep*.json"))):
        rec = json.loads(Path(p).read_text(encoding="utf-8"))
        if not rec.get("main_id"):
            continue
        eid = Path(p).stem
        lesson = json.loads((BASE_DIR / "lessons" / f"{eid}.json").read_text(encoding="utf-8"))
        out.append({"ep": eid, "title": lesson["title_ja"], "main": rec["main_id"], "short": rec.get("short_id"),
                    "publish_at": rec.get("publish_at")})
    return out


def api():
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=creds())


def query(a, start, end, metrics, dimensions=None, filters=None, sort=None, max_results=None):
    kw = dict(ids=f"channel=={CHANNEL_ID}", startDate=start, endDate=end, metrics=metrics)
    if dimensions:
        kw["dimensions"] = dimensions
    if filters:
        kw["filters"] = filters
    if sort:
        kw["sort"] = sort
    if max_results:
        kw["maxResults"] = max_results
    resp = a.reports().query(**kw).execute()
    names = [c["name"] for c in resp.get("columnHeaders", [])]
    return [dict(zip(names, r)) for r in resp.get("rows", [])]


def reach() -> dict:
    """Reporting API のレポートから、動画ごとのインプレッションとクリック数。"""
    agg = defaultdict(lambda: {"impressions": 0, "clicks": 0.0})
    for f in glob.glob(str(RAW_DIR / "learn-reach" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                n = int(row["video_thumbnail_impressions"])
                agg[row["video_id"]]["impressions"] += n
                agg[row["video_id"]]["clicks"] += n * float(row["video_thumbnail_impressions_ctr"])
    return agg


def collect() -> dict:
    a = api()
    eps = episodes()
    rc = reach()
    today = date.today().isoformat()
    start = "2026-10-01"
    result = {"asof": today, "episodes": []}
    for e in eps:
        item = {"ep": e["ep"], "title": e["title"], "publish_at": e["publish_at"], "main": {}, "short": {}}
        for kind, vid in (("main", e["main"]), ("short", e["short"])):
            if not vid:
                continue
            m = query(a, start, today, "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments",
                      "video", f"video=={vid}")
            d = m[0] if m else {}
            r = rc.get(vid, {"impressions": 0, "clicks": 0.0})
            d["impressions"] = r["impressions"]
            d["ctr"] = (r["clicks"] / r["impressions"]) if r["impressions"] else None
            d["video_id"] = vid
            if m:
                d["traffic"] = query(a, start, today, "views,estimatedMinutesWatched", "insightTrafficSourceType",
                                     f"video=={vid}", sort="-views")
                d["country"] = query(a, start, today, "views", "country", f"video=={vid}", sort="-views", max_results=5)
                d["device"] = query(a, start, today, "views", "deviceType", f"video=={vid}", sort="-views")
                if kind == "main":
                    d["retention"] = query(a, start, today, "audienceWatchRatio,relativeRetentionPerformance",
                                           "elapsedVideoTimeRatio", f"video=={vid}")
            item[kind] = d
        result["episodes"].append(item)
    # チャンネル全体: 日別の視聴（公開の時間帯の判断用に、視聴の多い日）
    result["channel_daily"] = query(a, start, today, "views,estimatedMinutesWatched,subscribersGained", "day", sort="day")
    return result


def pct(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def show(res: dict, retention_only=False):
    print(f"━━━ 学習版アナリティクス（{res['asof']} 時点。データは2〜3日遅れ）━━━")
    if not retention_only:
        print("\n【本編】回 / 視聴 / 視聴時間(分) / 平均視聴(分) / 平均視聴率 / 登録者 / インプレ / CTR")
        for e in res["episodes"]:
            m = e["main"]
            if not m.get("views") and not m.get("impressions"):
                print(f"  {e['ep']} {e['title']}: データなし（公開予定 {e['publish_at']}）")
                continue
            print(f"  {e['ep']} {e['title']}: {m.get('views', 0)} / {m.get('estimatedMinutesWatched', 0):.0f} / "
                  f"{m.get('averageViewDuration', 0) / 60:.1f} / {m.get('averageViewPercentage', 0):.1f}% / "
                  f"{m.get('subscribersGained', 0)} / {m.get('impressions', 0)} / {pct(m.get('ctr'))}")
        print("\n【ショート】回 / 視聴 / 平均視聴率 / 登録者")
        for e in res["episodes"]:
            s = e["short"]
            if s.get("views"):
                print(f"  {e['ep']}: {s['views']} / {s.get('averageViewPercentage', 0):.1f}% / {s.get('subscribersGained', 0)}")
        print("\n【流入経路（本編）】")
        for e in res["episodes"]:
            t = e["main"].get("traffic")
            if t:
                print(f"  {e['ep']}: " + ", ".join(f"{r['insightTrafficSourceType']}={r['views']}" for r in t[:6]))
        print("\n【国（本編）】")
        for e in res["episodes"]:
            c = e["main"].get("country")
            if c:
                print(f"  {e['ep']}: " + ", ".join(f"{r['country']}={r['views']}" for r in c))
    print("\n【維持率の曲線（本編。動画の長さの何割の所で、何割の視聴者が残っているか）】")
    for e in res["episodes"]:
        ret = e["main"].get("retention")
        if not ret:
            continue
        pts = []
        for p in RETENTION_POINTS:
            near = min(ret, key=lambda r: abs(r["elapsedVideoTimeRatio"] - p))
            pts.append(f"{int(p * 100)}%地点={near['audienceWatchRatio'] * 100:.0f}%")
        print(f"  {e['ep']}: " + " / ".join(pts))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retention", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = collect()
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    else:
        show(res, a.retention)


if __name__ == "__main__":
    main()
