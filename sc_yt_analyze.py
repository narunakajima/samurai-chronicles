#!/usr/bin/env python3
"""
sc_yt_analyze.py — analytics/raw/ のCSVを動画別に集計し、相対パフォーマンスを分析する

使い方:
  python3 sc_yt_analyze.py                      # 全動画の集計表を表示
  python3 sc_yt_analyze.py --top 10              # CTR・維持率の上位/下位N件
  python3 sc_yt_analyze.py --min-impressions 500 # 集計対象の最低インプレッション数

前提: 先に `python3 sc_yt_download_reports.py` でCSVを最新化しておくこと。
"""

import argparse
import csv
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent
ANALYTICS_DIR = BASE_DIR / "analytics" / "raw"


def build_episode_map() -> dict:
    """video_id -> {episode_id, title} のマッピングを episodes/*.json から構築する。"""
    ep_map = {}
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        url = d.get("youtube_url", "")
        vid = url.rstrip("/").split("/")[-1] if url else None
        if vid:
            ep_map[vid] = {
                "episode_id": d.get("episode_id"),
                "title": d.get("youtube_title", ""),
            }
    return ep_map


def aggregate_reach() -> dict:
    """channel_reach_basic_a1 から video_id別のインプレッション・クリック数を集計する。"""
    agg = defaultdict(lambda: {"impressions": 0, "clicks": 0.0})
    for f in glob.glob(str(ANALYTICS_DIR / "channel_reach_basic_a1" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                vid = row["video_id"]
                impr = int(row["video_thumbnail_impressions"])
                ctr = float(row["video_thumbnail_impressions_ctr"])
                agg[vid]["impressions"] += impr
                agg[vid]["clicks"] += impr * ctr
    return agg


def aggregate_combined() -> dict:
    """channel_combined_a3 から video_id別の視聴数・視聴時間・維持率を集計する。"""
    agg = defaultdict(lambda: {"views": 0, "watch_min": 0.0, "avg_pct_sum": 0.0, "avg_pct_n": 0})
    for f in glob.glob(str(ANALYTICS_DIR / "channel_combined_a3" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                vid = row["video_id"]
                views = int(row["views"])
                watch = float(row["watch_time_minutes"])
                avg_pct = float(row["average_view_duration_percentage"])
                agg[vid]["views"] += views
                agg[vid]["watch_min"] += watch
                if views > 0:
                    agg[vid]["avg_pct_sum"] += avg_pct * views
                    agg[vid]["avg_pct_n"] += views
    return agg


def build_stats() -> list:
    """エピソードごとの統計をまとめたリストを返す（episode_id昇順）。"""
    ep_map = build_episode_map()
    reach = aggregate_reach()
    combined = aggregate_combined()

    results = []
    all_vids = set(reach.keys()) | set(combined.keys())
    for vid in all_vids:
        ep = ep_map.get(vid)
        if not ep:
            continue
        r = reach.get(vid, {"impressions": 0, "clicks": 0.0})
        c = combined.get(vid, {"views": 0, "watch_min": 0.0, "avg_pct_sum": 0.0, "avg_pct_n": 0})
        ctr = (r["clicks"] / r["impressions"] * 100) if r["impressions"] > 0 else 0
        avg_pct = (c["avg_pct_sum"] / c["avg_pct_n"]) if c["avg_pct_n"] > 0 else 0
        results.append({
            "episode_id": ep["episode_id"],
            "title": ep["title"][:50],
            "impressions": int(r["impressions"]),
            "ctr": round(ctr, 2),
            "views": c["views"],
            "watch_hours": round(c["watch_min"] / 60, 1),
            "avg_view_pct": round(avg_pct, 1),
        })

    results.sort(key=lambda x: x["episode_id"])
    return results


def classify_title(title: str) -> str:
    t = title.strip()
    if t.startswith("Why"):
        return "型B(Why)"
    if t.startswith("The Real Reason"):
        return "型C(Real Reason)"
    if re.match(r"^The \w+ (Who|That)", t):
        return "型A/D(The X Who/That)"
    if re.match(r"^\d", t):
        return "数字始まり"
    if "?" in t[:60]:
        return "疑問形"
    return "その他"


def print_main_table(results: list):
    print(f"\n集計動画数: {len(results)}本\n")
    print(f"{'ep':6} {'impr':>6} {'CTR%':>6} {'views':>6} {'whrs':>6} {'avgview%':>8}  title")
    for r in results:
        print(f"{r['episode_id']:6} {r['impressions']:6} {r['ctr']:6.2f} {r['views']:6} "
              f"{r['watch_hours']:6.1f} {r['avg_view_pct']:8.1f}  {r['title']}")


def print_top_bottom(results: list, n: int, min_impressions: int, min_views: int):
    filtered_ctr = [r for r in results if r["impressions"] >= min_impressions]
    filtered_view = [r for r in results if r["views"] >= min_views]

    print(f"\n=== CTR上位{n}（impr{min_impressions}+） ===")
    for r in sorted(filtered_ctr, key=lambda x: -x["ctr"])[:n]:
        print(f"{r['episode_id']} CTR={r['ctr']}% impr={r['impressions']} "
              f"views={r['views']} avgview%={r['avg_view_pct']}  {r['title']}")

    print(f"\n=== CTR下位{n}（impr{min_impressions}+） ===")
    for r in sorted(filtered_ctr, key=lambda x: x["ctr"])[:n]:
        print(f"{r['episode_id']} CTR={r['ctr']}% impr={r['impressions']} "
              f"views={r['views']} avgview%={r['avg_view_pct']}  {r['title']}")

    print(f"\n=== 視聴維持率上位{n}（views{min_views}+） ===")
    for r in sorted(filtered_view, key=lambda x: -x["avg_view_pct"])[:n]:
        print(f"{r['episode_id']} avgview%={r['avg_view_pct']} views={r['views']} "
              f"CTR={r['ctr']}%  {r['title']}")

    print(f"\n=== 視聴維持率下位{n}（views{min_views}+） ===")
    for r in sorted(filtered_view, key=lambda x: x["avg_view_pct"])[:n]:
        print(f"{r['episode_id']} avgview%={r['avg_view_pct']} views={r['views']} "
              f"CTR={r['ctr']}%  {r['title']}")

    if filtered_ctr:
        avg_ctr = sum(r["ctr"] for r in filtered_ctr) / len(filtered_ctr)
        print(f"\n平均CTR（impr{min_impressions}+）: {avg_ctr:.2f}%")
    if filtered_view:
        avg_view = sum(r["avg_view_pct"] for r in filtered_view) / len(filtered_view)
        print(f"平均維持率（views{min_views}+）: {avg_view:.1f}%")


def print_title_pattern_breakdown(results: list, min_impressions: int, min_views: int):
    r_by_ep = {r["episode_id"]: r for r in results}
    by_type = defaultdict(list)
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        ep_id = d.get("episode_id")
        r = r_by_ep.get(ep_id)
        if not r or r["impressions"] < min_impressions:
            continue
        ttype = classify_title(d.get("youtube_title", ""))
        by_type[ttype].append(r)

    print(f"\n=== タイトル型別パフォーマンス（impr{min_impressions}+） ===")
    for ttype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        avg_ctr = sum(i["ctr"] for i in items) / len(items)
        view_items = [i for i in items if i["views"] >= min_views]
        avg_view = sum(i["avg_view_pct"] for i in view_items) / len(view_items) if view_items else 0
        print(f"{ttype}: n={len(items)}  平均CTR={avg_ctr:.2f}%  平均維持率={avg_view:.1f}%")


def print_character_count_breakdown(results: list, min_impressions: int):
    r_by_ep = {r["episode_id"]: r for r in results}
    by_n = defaultdict(list)
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        ep_id = d.get("episode_id")
        r = r_by_ep.get(ep_id)
        if not r or r["impressions"] < min_impressions:
            continue
        scenes = d.get("scenes", [])
        n_chars = len(set(s.get("character_ref") for s in scenes if s.get("character_ref")))
        bucket = "1人" if n_chars <= 1 else ("2人" if n_chars == 2 else "3人以上")
        by_n[bucket].append(r["ctr"])

    print(f"\n=== 登場人物数別 CTR（impr{min_impressions}+） ===")
    for bucket in ["1人", "2人", "3人以上"]:
        items = by_n.get(bucket, [])
        if items:
            print(f"{bucket}: n={len(items)}  平均CTR={sum(items)/len(items):.2f}%")


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles YouTube アナリティクス集計")
    parser.add_argument("--top", type=int, default=10, help="上位/下位表示件数（デフォルト10）")
    parser.add_argument("--min-impressions", type=int, default=500,
                        help="CTR比較の最低インプレッション数（デフォルト500）")
    parser.add_argument("--min-views", type=int, default=20,
                        help="維持率比較の最低視聴数（デフォルト20）")
    parser.add_argument("--full", action="store_true", help="全動画の一覧表も表示する")
    args = parser.parse_args()

    results = build_stats()
    if not results:
        print("❌ 集計対象データがありません。先に sc_yt_download_reports.py を実行してください。")
        return

    if args.full:
        print_main_table(results)
    print_top_bottom(results, args.top, args.min_impressions, args.min_views)
    print_title_pattern_breakdown(results, args.min_impressions, args.min_views)
    print_character_count_breakdown(results, args.min_impressions)


if __name__ == "__main__":
    cli()
