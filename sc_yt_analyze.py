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
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
ANALYTICS_DIR = BASE_DIR / "analytics" / "raw"

# 2026-08-04改訂（Opusによる分析監査を受けての修正）:
# n<=5の区分は95%CIが全体平均と区別できないほど広く、数値を出すと誤読を誘発するため
# 「測定不能」扱いにする。
MIN_BUCKET_N = 6


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


def aggregate_daily_reach() -> dict:
    """(video_id, 'YYYYMMDD') -> {impressions, clicks} の日次集計を返す（年齢調整済み指標用）。"""
    daily = defaultdict(lambda: {"impressions": 0, "clicks": 0.0})
    for f in glob.glob(str(ANALYTICS_DIR / "channel_reach_basic_a1" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                vid = row["video_id"]
                d = row["date"]
                impr = int(row["video_thumbnail_impressions"])
                ctr = float(row["video_thumbnail_impressions_ctr"])
                key = (vid, d)
                daily[key]["impressions"] += impr
                daily[key]["clicks"] += impr * ctr
    return daily


def build_publish_dates() -> dict:
    """episode_id -> 'YYYYMMDD' の公開日マップ。scheduled_atが無いエピソードは含めない
    （公開日が特定できないため、年齢調整済み指標から安全に除外する）。"""
    pub = {}
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        sched = d.get("scheduled_at")
        if not sched:
            continue
        date_part = sched.split(" ")[0].replace("-", "")
        pub[d.get("episode_id")] = date_part
    return pub


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


def title_for_classification(episode_json: dict) -> str:
    """型分類に使うべきタイトルを返す。

    2026-08-04修正: リタイトルされた動画（`youtube_title_history`あり）は、
    現在のタイトルではなく最初のタイトル（旧タイトル）で分類する。
    リタイトルは通常公開からしばらく経ってから行われ、その時点までに
    インプレッションの大半（実績上92〜94%）が旧タイトルで発生しているため、
    現在のタイトルで分類するとリタイトル前の実績が新ラベルに誤って
    帰属してしまう（2026-08-02分析で発生した「型A/D CTR逆転」はこのバグが
    原因のアーティファクトだった）。
    """
    history = episode_json.get("youtube_title_history")
    if history:
        return history[0].get("title", episode_json.get("youtube_title", ""))
    return episode_json.get("youtube_title", "")


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
        print(f"\n平均CTR（impr{min_impressions}+、n={len(filtered_ctr)}）: {avg_ctr:.2f}%")
    if filtered_view:
        avg_view = sum(r["avg_view_pct"] for r in filtered_view) / len(filtered_view)
        print(f"平均維持率（views{min_views}+、n={len(filtered_view)}）: {avg_view:.1f}%")


def print_title_pattern_breakdown(results: list, min_impressions: int, min_views: int):
    r_by_ep = {r["episode_id"]: r for r in results}
    by_type = defaultdict(list)
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        ep_id = d.get("episode_id")
        r = r_by_ep.get(ep_id)
        if not r or r["impressions"] < min_impressions:
            continue
        ttype = classify_title(title_for_classification(d))
        by_type[ttype].append(r)

    print(f"\n=== タイトル型別パフォーマンス（impr{min_impressions}+、リタイトル動画は旧タイトルで分類） ===")
    for ttype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(items) < MIN_BUCKET_N:
            print(f"{ttype}: n={len(items)}  測定不能（サンプル不足、n<{MIN_BUCKET_N}）")
            continue
        avg_ctr = sum(i["ctr"] for i in items) / len(items)
        view_items = [i for i in items if i["views"] >= min_views]
        if len(view_items) < MIN_BUCKET_N:
            print(f"{ttype}: n={len(items)}  平均CTR={avg_ctr:.2f}%  維持率は測定不能（n<{MIN_BUCKET_N}）")
            continue
        avg_view = sum(i["avg_view_pct"] for i in view_items) / len(view_items)
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

    print(f"\n=== 登場人物数別 CTR（impr{min_impressions}+、character_refのユニーク数＝画像アセット数の代理指標） ===")
    for bucket in ["1人", "2人", "3人以上"]:
        items = by_n.get(bucket, [])
        if not items:
            continue
        if len(items) < MIN_BUCKET_N:
            print(f"{bucket}: n={len(items)}  測定不能（サンプル不足、n<{MIN_BUCKET_N}）")
            continue
        print(f"{bucket}: n={len(items)}  平均CTR={sum(items)/len(items):.2f}%")


def print_age_adjusted(results: list, window_days: int = 14):
    """公開後window_days日間の累計インプレッション・CTR（年齢を揃えた比較）。
    累計値による比較は「新しい動画ほど不利/有利」というバイアスが混ざるため、
    こちらを優先して使うこと（2026-08-04追加）。"""
    ep_map = build_episode_map()
    vid_by_ep = {v["episode_id"]: k for k, v in ep_map.items()}
    pub_dates = build_publish_dates()
    daily = aggregate_daily_reach()

    vids_last_date = defaultdict(str)
    for (vid, d) in daily.keys():
        if d > vids_last_date[vid]:
            vids_last_date[vid] = d

    rows = []
    skipped_no_date = 0
    skipped_too_new = 0
    for r in results:
        ep_id = r["episode_id"]
        vid = vid_by_ep.get(ep_id)
        pub = pub_dates.get(ep_id)
        if not vid or not pub:
            skipped_no_date += 1
            continue
        start = date(int(pub[:4]), int(pub[4:6]), int(pub[6:8]))
        window_end = start + timedelta(days=window_days - 1)
        if vids_last_date.get(vid, "") < window_end.strftime("%Y%m%d"):
            skipped_too_new += 1
            continue
        impr_sum, click_sum = 0, 0.0
        for i in range(window_days):
            day_str = (start + timedelta(days=i)).strftime("%Y%m%d")
            cell = daily.get((vid, day_str))
            if cell:
                impr_sum += cell["impressions"]
                click_sum += cell["clicks"]
        ctr14 = (click_sum / impr_sum * 100) if impr_sum > 0 else 0
        rows.append({"episode_id": ep_id, "impr": impr_sum, "ctr": round(ctr14, 2)})

    print(f"\n=== 公開後{window_days}日 年齢調整済みインプレ・CTR ===")
    print(f"（公開日不明のため除外: {skipped_no_date}件／{window_days}日分のデータがまだ揃っていないため除外: {skipped_too_new}件）")
    if not rows:
        print("  算出できる動画がありませんでした")
        return
    avg_impr = sum(r["impr"] for r in rows) / len(rows)
    avg_ctr = sum(r["ctr"] for r in rows) / len(rows)
    print(f"  対象: {len(rows)}本  平均インプレ: {avg_impr:.0f}  平均CTR: {avg_ctr:.2f}%")
    for r in sorted(rows, key=lambda x: x["episode_id"]):
        print(f"  {r['episode_id']}  impr={r['impr']:5}  CTR={r['ctr']}%")


def print_monthly_channel_summary():
    """チャンネル全体の月次インプレッション・視聴数（構造的な露出トレンド把握用、2026-08-04追加）。
    個別動画の最適化議論の前に、まずチャンネル全体の露出が増えているかを確認するために使う。"""
    monthly_impr = defaultdict(int)
    monthly_views = defaultdict(int)
    for f in glob.glob(str(ANALYTICS_DIR / "channel_reach_basic_a1" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                monthly_impr[row["date"][:6]] += int(row["video_thumbnail_impressions"])
    for f in glob.glob(str(ANALYTICS_DIR / "channel_combined_a3" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                monthly_views[row["date"][:6]] += int(row["views"])

    print("\n=== チャンネル全体 月次露出トレンド ===")
    for ym in sorted(set(monthly_impr) | set(monthly_views)):
        impr = monthly_impr.get(ym, 0)
        views = monthly_views.get(ym, 0)
        print(f"  {ym[:4]}-{ym[4:]}: インプレ={impr:,}  視聴={views:,}")


def cli():
    parser = argparse.ArgumentParser(description="Samurai Chronicles YouTube アナリティクス集計")
    parser.add_argument("--top", type=int, default=10, help="上位/下位表示件数（デフォルト10）")
    parser.add_argument("--min-impressions", type=int, default=1500,
                        help="CTR比較の最低インプレッション数（デフォルト1500。"
                             "2026-08-04改訂: 500だと実クリック15回程度で検出力不足のため引き上げ）")
    parser.add_argument("--min-views", type=int, default=50,
                        help="維持率比較の最低視聴数（デフォルト50。2026-08-04改訂: 20から引き上げ）")
    parser.add_argument("--full", action="store_true", help="全動画の一覧表も表示する")
    parser.add_argument("--no-age-adjusted", action="store_true",
                        help="公開後14日の年齢調整済み指標をスキップする")
    parser.add_argument("--no-monthly", action="store_true",
                        help="チャンネル全体の月次露出トレンドをスキップする")
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
    if not args.no_age_adjusted:
        print_age_adjusted(results)
    if not args.no_monthly:
        print_monthly_channel_summary()


if __name__ == "__main__":
    cli()
