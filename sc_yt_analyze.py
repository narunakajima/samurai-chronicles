#!/usr/bin/env python3
"""
sc_yt_analyze.py — Google Drive samurai-chronicles/analytics/raw/ のCSVを動画別に集計し、相対パフォーマンスを分析する

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
import random
import re
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).parent
# 2026-10-04: 保存先をGoogle Driveの同期フォルダに移した（MacBook・iMacで共有するため。
# Reporting APIは古いレポートを一定期間で消すので、どちらの端末で取得した分も1か所に残す。
# くらしを変える科学（kagaku-life）と同じ構成）
GDRIVE_ROOT = (
    Path.home()
    / "Library"
    / "CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)
ANALYTICS_DIR = GDRIVE_ROOT / "analytics" / "raw"

# 2026-08-04改訂（Opusによる分析監査を受けての修正）:
# n<=5の区分は95%CIが全体平均と区別できないほど広く、数値を出すと誤読を誘発するため
# 「測定不能」扱いにする。
MIN_BUCKET_N = 6

# 2026-10-14: 流入経路コードの名称（YouTube Reporting API公式ドキュメント
# https://developers.google.com/youtube/reporting/v1/reports/dimensions の
# traffic_source_type 表。Opus検証とWebFetchの2回で同じ結果を確認）。
# 表にないコードは名称を付けず「名称未定義」と表示する（憶測でラベル付けしない）。
TRAFFIC_SOURCE_NAMES = {
    "0": "Direct or unknown", "1": "YouTube advertising", "3": "Browse features",
    "4": "YouTube channels", "5": "YouTube search", "7": "Suggested videos",
    "8": "Other YouTube features", "9": "External", "11": "Video cards and annotations",
    "14": "Playlists", "17": "Notifications", "18": "Playlist pages",
    "19": "Programming from claimed content", "20": "Interactive video endscreen",
    "23": "Stories", "24": "Shorts", "25": "Product Pages", "26": "Hashtag Pages",
    "27": "Sound Pages", "28": "Live redirect", "29": "Podcasts", "30": "Remixed video",
    "31": "Vertical live feed", "32": "Related video (Shorts player)",
}


def traffic_name(code: str) -> str:
    name = TRAFFIC_SOURCE_NAMES.get(str(code))
    return f"code={code} {name}" if name else f"code={code}（名称未定義）"


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
    """channel_combined_a3 から video_id別の視聴数・エンゲージ視聴数・視聴時間・維持率を集計する。

    2026-09-28修正（Opus月次分析で発覚）: 2026-08-27以降、フィード内の数秒だけの
    再生（サムネイルクリックを伴わない）が`views`に大量計上されるようになり、
    views加重の維持率・views基準のフィルタが実態を反映しなくなった
    （例: ep078はviews1161だがengaged_viewsは142のみ）。`engaged_views`は
    この影響を受けず連続的に推移しているため、維持率の分母・フィルタ基準は
    engaged_viewsに切り替える。"""
    agg = defaultdict(lambda: {
        "views": 0, "engaged": 0, "watch_min": 0.0, "avg_pct_sum": 0.0, "avg_pct_n": 0,
        "ns_engaged": 0, "ns_pct_sum": 0.0,
    })
    for f in glob.glob(str(ANALYTICS_DIR / "channel_combined_a3" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                vid = row["video_id"]
                views = int(row["views"])
                engaged = int(row["engaged_views"])
                watch = float(row["watch_time_minutes"])
                avg_pct = float(row["average_view_duration_percentage"])
                agg[vid]["views"] += views
                agg[vid]["engaged"] += engaged
                agg[vid]["watch_min"] += watch
                if engaged > 0:
                    agg[vid]["avg_pct_sum"] += avg_pct * engaged
                    agg[vid]["avg_pct_n"] += engaged
                    # 2026-10-14: 登録者は非登録者より1視聴あたりの視聴時間が数倍長く、
                    # 登録者比率の変化が維持率の見かけの変化を作る（Opus分析）。維持率の
                    # 比較は非登録者（not_subscribed）に限った値を使う。
                    if row["subscribed_status"] == "not_subscribed":
                        agg[vid]["ns_engaged"] += engaged
                        agg[vid]["ns_pct_sum"] += avg_pct * engaged
    return agg


def aggregate_daily_combined() -> dict:
    """(video_id, 'YYYYMMDD', subscribed_status) -> {engaged, watch_min}。
    14日窓内の「登録者比率」「非登録者の1engagedあたり視聴秒数」の算出用（2026-10-14追加）。"""
    daily = defaultdict(lambda: {"engaged": 0, "watch_min": 0.0})
    for f in glob.glob(str(ANALYTICS_DIR / "channel_combined_a3" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row["video_id"], row["date"], row["subscribed_status"])
                daily[key]["engaged"] += int(row["engaged_views"])
                daily[key]["watch_min"] += float(row["watch_time_minutes"])
    return daily


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


def aggregate_acquisition() -> dict:
    """channel_combined_a3 から video_id別に subscribed_status・traffic_source_type別の
    engaged_views を集計する。

    2026-09-06追加（Fable監査対応）: 「有名人物は検索流入の受け皿になる」（sc-new.md
    L128）等の視聴者獲得系の仮説が、これまで`traffic_source_type`/`subscribed_status`
    列（CSVには存在する）を一度も使わずに検証不能なまま放置されていたため追加した。

    2026-09-28修正（Opus月次分析で発覚）: viewsは8/27以降のフィード内再生の影響を
    受けるため、engaged_viewsに切り替える。`subscribed_status=unknown`は
    新規/既存の判定材料にならないため分母（known_engaged）から除外する。
    """
    agg = defaultdict(lambda: {
        "views": 0, "engaged": 0, "known_engaged": 0, "unsubscribed_engaged": 0,
        "traffic": defaultdict(int),
    })
    for f in glob.glob(str(ANALYTICS_DIR / "channel_combined_a3" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                vid = row["video_id"]
                engaged = int(row["engaged_views"])
                agg[vid]["views"] += int(row["views"])
                agg[vid]["engaged"] += engaged
                status = row["subscribed_status"]
                if status != "unknown":
                    agg[vid]["known_engaged"] += engaged
                    if status == "not_subscribed":
                        agg[vid]["unsubscribed_engaged"] += engaged
                agg[vid]["traffic"][row["traffic_source_type"]] += engaged
    return agg


def build_publish_dates() -> dict:
    """episode_id -> 'YYYYMMDD' の公開日マップ（scheduled_at基準、JST日付）。
    scheduled_atが無いエピソードは含めない（公開日が特定できないため、
    年齢調整済み指標から安全に除外する）。

    ⚠️ この日付はJST基準であり、YouTube ReportingのCSVはPacific時間基準の
    日付で記録されるため、実際の初回インプレッションは前日にずれることが多い
    （2026-09-28発覚、`build_first_impression_dates()`参照）。14日窓の起点には
    このJST日付ではなく`build_first_impression_dates()`を優先して使うこと。
    """
    pub = {}
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        sched = d.get("scheduled_at")
        if not sched:
            continue
        date_part = sched.split(" ")[0].replace("-", "")
        pub[d.get("episode_id")] = date_part
    return pub


def build_pacific_publish_dates() -> dict:
    """episode_id -> 'YYYYMMDD'（公開予定時刻をPacific時間に直した日付）。

    2026-10-14追加（Opus月次分析で発覚）: Reporting APIのCSV日付はPacific時間基準。
    JST 03:00公開（火木土の標準枠）はPacific前日の午前になり、`scheduled_at`のJST日付とは
    1日ずれる。14日窓の有効性判定（初日が欠損日に当たっていないか）には、JSTの日付ではなく
    こちらを使う。`scheduled_at`に時刻がなければ03:00 JSTとみなす。"""
    jst, pac = ZoneInfo("Asia/Tokyo"), ZoneInfo("America/Los_Angeles")
    out = {}
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        sched = d.get("scheduled_at")
        if not sched:
            continue
        parts = sched.split(" ")
        hhmm = parts[1][:5] if len(parts) > 1 else "03:00"
        try:
            dt = datetime.strptime(f"{parts[0]} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=jst)
        except ValueError:
            continue
        out[d.get("episode_id")] = dt.astimezone(pac).strftime("%Y%m%d")
    return out


def build_first_impression_dates(daily: dict) -> dict:
    """video_id -> 実際に最初にインプレッションが記録された日付('YYYYMMDD')。

    2026-09-28追加（Opus月次分析で発覚）: 従来`print_age_adjusted`は
    `scheduled_at`のJST日付をそのまま14日窓の起点にしていたが、YouTube
    ReportingのCSV日付はPacific時間基準のため、84本中76本で初回インプレッションが
    「scheduled_atの前日」に記録されていた（公開初日を窓から落としていた＝
    窓内インプレッションの中央値で約5.7%を毎回取りこぼす体系的なバグ）。
    実際に記録された最初のインプレッション日を起点にすることで解消する。
    """
    first = {}
    for (vid, d) in daily.keys():
        if vid not in first or d < first[vid]:
            first[vid] = d
    return first


def build_shorts_map() -> dict:
    """video_id(Shorts) -> episode_id のマッピング（`shorts_url`から）。"""
    m = {}
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        url = d.get("shorts_url", "")
        vid = url.rstrip("/").split("/")[-1] if url else None
        if vid:
            m[vid] = d.get("episode_id")
    return m


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
        c = combined.get(vid, {
            "views": 0, "engaged": 0, "watch_min": 0.0, "avg_pct_sum": 0.0, "avg_pct_n": 0,
            "ns_engaged": 0, "ns_pct_sum": 0.0,
        })
        ctr = (r["clicks"] / r["impressions"] * 100) if r["impressions"] > 0 else 0
        avg_pct = (c["avg_pct_sum"] / c["avg_pct_n"]) if c["avg_pct_n"] > 0 else 0
        ns_pct = (c["ns_pct_sum"] / c["ns_engaged"]) if c["ns_engaged"] > 0 else 0
        results.append({
            "episode_id": ep["episode_id"],
            "title": ep["title"][:50],
            "impressions": int(r["impressions"]),
            "ctr": round(ctr, 2),
            "views": c["views"],
            "engaged": c["engaged"],
            "watch_hours": round(c["watch_min"] / 60, 1),
            "avg_view_pct": round(avg_pct, 1),
            "ns_engaged": c["ns_engaged"],
            "ns_avg_view_pct": round(ns_pct, 1),
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
    print(f"{'ep':6} {'impr':>6} {'CTR%':>6} {'views':>6} {'engaged':>7} {'whrs':>6} {'avgview%':>8}  title")
    for r in results:
        print(f"{r['episode_id']:6} {r['impressions']:6} {r['ctr']:6.2f} {r['views']:6} "
              f"{r['engaged']:7} {r['watch_hours']:6.1f} {r['avg_view_pct']:8.1f}  {r['title']}")


def print_top_bottom(results: list, n: int, min_impressions: int, min_engaged: int):
    """
    2026-09-28修正: 維持率側のフィルタ・上位下位表示は`views`ではなく`engaged`
    （engaged_views）基準に切り替えた（8/27以降views水増しの影響を受けるため）。
    """
    filtered_ctr = [r for r in results if r["impressions"] >= min_impressions]
    filtered_view = [r for r in results if r["engaged"] >= min_engaged]

    print(f"\n=== CTR上位{n}（impr{min_impressions}+） ===")
    for r in sorted(filtered_ctr, key=lambda x: -x["ctr"])[:n]:
        print(f"{r['episode_id']} CTR={r['ctr']}% impr={r['impressions']} "
              f"views={r['views']} engaged={r['engaged']} avgview%={r['avg_view_pct']}  {r['title']}")

    print(f"\n=== CTR下位{n}（impr{min_impressions}+） ===")
    for r in sorted(filtered_ctr, key=lambda x: x["ctr"])[:n]:
        print(f"{r['episode_id']} CTR={r['ctr']}% impr={r['impressions']} "
              f"views={r['views']} engaged={r['engaged']} avgview%={r['avg_view_pct']}  {r['title']}")

    # 2026-10-14: 維持率は非登録者に限った値でランキングする（登録者は1視聴あたりの視聴時間が
    # 数倍長く、登録者比率が高い回が見かけ上「維持率が高い」になるため。全視聴者の値は併記のみ）
    ns_view = [r for r in results if r["ns_engaged"] >= min_engaged]
    print(f"\n=== 視聴維持率上位{n}（非登録者のみ、非登録者engaged{min_engaged}+。()内は全視聴者の値） ===")
    for r in sorted(ns_view, key=lambda x: -x["ns_avg_view_pct"])[:n]:
        print(f"{r['episode_id']} 非登録者avgview%={r['ns_avg_view_pct']} (全体{r['avg_view_pct']}) "
              f"非登録者engaged={r['ns_engaged']} CTR={r['ctr']}%  {r['title']}")

    print(f"\n=== 視聴維持率下位{n}（非登録者のみ、非登録者engaged{min_engaged}+） ===")
    for r in sorted(ns_view, key=lambda x: x["ns_avg_view_pct"])[:n]:
        print(f"{r['episode_id']} 非登録者avgview%={r['ns_avg_view_pct']} (全体{r['avg_view_pct']}) "
              f"非登録者engaged={r['ns_engaged']} CTR={r['ctr']}%  {r['title']}")

    if filtered_ctr:
        avg_ctr = sum(r["ctr"] for r in filtered_ctr) / len(filtered_ctr)
        print(f"\n平均CTR（impr{min_impressions}+、n={len(filtered_ctr)}）: {avg_ctr:.2f}%")
    if ns_view:
        avg_ns = sum(r["ns_avg_view_pct"] for r in ns_view) / len(ns_view)
        print(f"平均維持率（非登録者のみ、非登録者engaged{min_engaged}+、n={len(ns_view)}）: {avg_ns:.1f}%")
    if filtered_view:
        avg_view = sum(r["avg_view_pct"] for r in filtered_view) / len(filtered_view)
        print(f"（参考）平均維持率（全視聴者、engaged{min_engaged}+、n={len(filtered_view)}）: {avg_view:.1f}%"
              f"　※登録者比率の影響を含む")


def print_title_pattern_breakdown(results: list, min_impressions: int, min_engaged: int):
    """
    ⚠️ 2026-09-28のOpus月次分析で、この累計値ベース・impr閾値ベースの比較には
    2つの構造的バイアスがあると判明した: (1) impr1500+のような閾値フィルタは
    露出という結果変数で選別する選択バイアスを持つ、(2) 累計CTRは古い動画ほど
    有利/不利になる年齢バイアスを持つ。**意思決定には`print_relative_category_breakdown`
    （月内相対CTR・14日窓ベース）を優先すること。** この関数は参考値として残す。
    """
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

    print(f"\n=== [参考値・選択/年齢バイアスあり] タイトル型別パフォーマンス"
          f"（impr{min_impressions}+、リタイトル動画は旧タイトルで分類） ===")
    for ttype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(items) < MIN_BUCKET_N:
            print(f"{ttype}: n={len(items)}  測定不能（サンプル不足、n<{MIN_BUCKET_N}）")
            continue
        avg_ctr = sum(i["ctr"] for i in items) / len(items)
        view_items = [i for i in items if i["engaged"] >= min_engaged]
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

    print(f"\n=== [参考値・選択/年齢バイアスあり] 登場人物数別 CTR"
          f"（impr{min_impressions}+、character_refのユニーク数＝画像アセット数の代理指標） ===")
    for bucket in ["1人", "2人", "3人以上"]:
        items = by_n.get(bucket, [])
        if not items:
            continue
        if len(items) < MIN_BUCKET_N:
            print(f"{bucket}: n={len(items)}  測定不能（サンプル不足、n<{MIN_BUCKET_N}）")
            continue
        print(f"{bucket}: n={len(items)}  平均CTR={sum(items)/len(items):.2f}%")


def compute_age_adjusted_rows(results: list, window_days: int = 14) -> tuple:
    """公開後window_days日間の累計インプレッション・CTRを行のリストで返す
    （`print_age_adjusted`と`print_relative_category_breakdown`で共用）。

    2026-09-28修正（Opus月次分析で発覚）: 窓の起点に`scheduled_at`のJST日付を
    そのまま使うと、YouTube ReportingのCSV日付はPacific時間基準のため、
    84本中76本で実際の初回インプレッションが「前日」に記録されていた
    （公開初日を毎回窓から取りこぼす体系的バグ）。実際に記録された最初の
    インプレッション日（`build_first_impression_dates`）を起点にする。

    2026-10-05修正（Opus月次分析で発覚）: Reporting APIのレポートは取得が漏れた日は
    二度と取り戻せず、7/11〜8/3（combined）・7/12,7/16〜8/6（reach）の約3.5週間が欠損している。
    従来は「窓の最終日以降のデータがあるか」だけで窓完了と判定していたため、窓の途中が
    欠けた動画（ep039〜050）や、初回インプレッションがデータ再開日の8/4になっている動画
    （ep051〜064、公開3〜19日目を測っていた）が「14日CTR」として集計され、ep052の8.82%等の
    無効な値が出ていた。次の2条件を満たす動画だけを有効な窓として扱う:
      (a) 窓の14日すべてについて、チャンネル全体のreachデータにその日付が存在する
      (b) 初回インプレッション日が公開予定日（scheduled_atのJST日付）の1日以内
          （Pacific時間基準の前日ずれを許容。データ再開日に切り詰められた動画を除外する）
    2026-10-14修正（Opus月次分析で発覚）: 上記(b)は「JSTの公開予定日±1日」で判定していたため、
    JST 03:00公開（Pacific前日）の動画で、Pacific公開日と翌日のreachが欠損日に当たり
    初日が欠けたまま、初回インプレッション日がJST日付の1日以内に収まって「有効」と
    扱われるケースがあった（ep066・ep067。正しい対象は55本でなく53本）。判定を
    (b') Pacific時間に直した公開日そのもの（`build_pacific_publish_dates`）が
         reachデータに存在し、初回インプレッション日がその日または翌日であること
    に改めた。あわせて各窓について、登録者比率と非登録者の1engagedあたり視聴秒数を算出する
    （登録者は非登録者より1視聴あたりの視聴時間が数倍長く、維持率の比較は非登録者に限る）。
    戻り値: (rows, skipped_no_date, skipped_too_new, skipped_gap)
    """
    ep_map = build_episode_map()
    vid_by_ep = {v["episode_id"]: k for k, v in ep_map.items()}
    pub_dates = build_publish_dates()
    pac_dates = build_pacific_publish_dates()
    daily = aggregate_daily_reach()
    daily_comb = aggregate_daily_combined()
    comb_dates = {d for (_v, d, _s) in daily_comb.keys()}
    first_impr = build_first_impression_dates(daily)

    vids_last_date = defaultdict(str)
    for (vid, d) in daily.keys():
        if d > vids_last_date[vid]:
            vids_last_date[vid] = d
    # チャンネル全体でreachデータが存在する日付（欠損日の判定用）
    present_dates = {d for (_v, d) in daily.keys()}

    rows = []
    skipped_no_date = 0
    skipped_too_new = 0
    skipped_gap = 0
    for r in results:
        ep_id = r["episode_id"]
        vid = vid_by_ep.get(ep_id)
        pub = pub_dates.get(ep_id)
        if not vid or not pub:
            skipped_no_date += 1
            continue
        start_str = first_impr.get(vid, pub)
        start = date(int(start_str[:4]), int(start_str[4:6]), int(start_str[6:8]))
        window_end = start + timedelta(days=window_days - 1)
        if vids_last_date.get(vid, "") < window_end.strftime("%Y%m%d"):
            skipped_too_new += 1
            continue
        pac = pac_dates.get(ep_id, pub)
        pac_d = date(int(pac[:4]), int(pac[4:6]), int(pac[6:8]))
        window_days_list = [(start + timedelta(days=i)).strftime("%Y%m%d") for i in range(window_days)]
        if (not 0 <= (start - pac_d).days <= 1 or pac not in present_dates
                or any(dd not in present_dates for dd in window_days_list)):
            skipped_gap += 1
            continue
        impr_sum, click_sum = 0, 0.0
        for i in range(window_days):
            day_str = (start + timedelta(days=i)).strftime("%Y%m%d")
            cell = daily.get((vid, day_str))
            if cell:
                impr_sum += cell["impressions"]
                click_sum += cell["clicks"]
        ctr14 = (click_sum / impr_sum * 100) if impr_sum > 0 else 0
        # 窓内の登録者比率・非登録者の1engagedあたり視聴秒数（combinedの全日付が揃う場合のみ）
        sub_ratio, ns_sec, ns_engaged14 = None, None, 0
        if all(dd in comb_dates for dd in window_days_list):
            eng = {"subscribed": 0, "not_subscribed": 0}
            ns_watch_min = 0.0
            for dd in window_days_list:
                for status in ("subscribed", "not_subscribed"):
                    cell = daily_comb.get((vid, dd, status))
                    if cell:
                        eng[status] += cell["engaged"]
                        if status == "not_subscribed":
                            ns_watch_min += cell["watch_min"]
            tot = eng["subscribed"] + eng["not_subscribed"]
            if tot > 0:
                sub_ratio = eng["subscribed"] / tot
            ns_engaged14 = eng["not_subscribed"]
            if ns_engaged14 > 0:
                ns_sec = ns_watch_min * 60 / ns_engaged14
        rows.append({
            "episode_id": ep_id, "impr": impr_sum, "clicks": click_sum,
            "ctr": round(ctr14, 2), "month": pub[:6],
            "sub_ratio": sub_ratio, "ns_sec": ns_sec, "ns_engaged14": ns_engaged14,
        })
    return rows, skipped_no_date, skipped_too_new, skipped_gap


def print_age_adjusted(results: list, window_days: int = 14):
    """公開後window_days日間の累計インプレッション・CTR（年齢を揃えた比較）。
    累計値による比較は「新しい動画ほど不利/有利」というバイアスが混ざるため、
    こちらを優先して使うこと（2026-08-04追加）。"""
    rows, skipped_no_date, skipped_too_new, skipped_gap = compute_age_adjusted_rows(results, window_days)

    print(f"\n=== 公開後{window_days}日 年齢調整済みインプレ・CTR ===")
    print(f"（公開日不明のため除外: {skipped_no_date}件／{window_days}日分のデータがまだ揃っていないため除外: {skipped_too_new}件／"
          f"データ欠損（7/11〜8/6）・初回インプレ日のずれで窓が無効のため除外: {skipped_gap}件）")
    if not rows:
        print("  算出できる動画がありませんでした")
        return
    avg_impr = sum(r["impr"] for r in rows) / len(rows)
    avg_ctr = sum(r["ctr"] for r in rows) / len(rows)
    print(f"  対象: {len(rows)}本  平均インプレ: {avg_impr:.0f}  平均CTR: {avg_ctr:.2f}%")
    print("  （登録者比率=窓内engagedに占める登録者の割合。非登録者秒=非登録者の1engagedあたり視聴秒数。"
          "維持率・視聴秒の比較は登録者比率の影響が大きいため非登録者秒を使うこと）")
    for r in sorted(rows, key=lambda x: x["episode_id"]):
        sr = f"{r['sub_ratio']*100:4.0f}%" if r["sub_ratio"] is not None else "  n/a"
        ns = f"{r['ns_sec']:4.0f}秒(n={r['ns_engaged14']})" if r["ns_sec"] is not None else "n/a"
        print(f"  {r['episode_id']}  impr={r['impr']:5}  clicks={r['clicks']:4.0f}  CTR={r['ctr']}%  "
              f"登録者比率={sr}  非登録者秒={ns}")


def print_monthly_channel_summary():
    """チャンネル全体の月次インプレッション・視聴数（構造的な露出トレンド把握用、2026-08-04追加）。
    個別動画の最適化議論の前に、まずチャンネル全体の露出が増えているかを確認するために使う。

    2026-09-28修正（Opus月次分析で発覚）: 「視聴」が見出し上「本編」のように読めるが、
    実際は本編・Shorts・未登録動画（主に初期のShorts等）が混在していた。
    本編/Shorts/未登録（views・engaged）に分けて表示する。
    """
    ep_map = build_episode_map()
    shorts_map = build_shorts_map()
    monthly_impr = defaultdict(int)          # 本編のみのインプレッション
    monthly_impr_other = defaultdict(int)    # 本編以外（Shorts・未登録動画）のインプレッション
    reach_days = defaultdict(set)            # 月ごとにreachデータが存在する日付
    combined_days = defaultdict(set)         # 月ごとにcombinedデータが存在する日付
    monthly = defaultdict(lambda: {
        "main_views": 0, "main_engaged": 0,
        "shorts_views": 0, "shorts_engaged": 0,
        "other_views": 0, "other_engaged": 0,
    })
    for f in glob.glob(str(ANALYTICS_DIR / "channel_reach_basic_a1" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ym = row["date"][:6]
                reach_days[ym].add(row["date"])
                impr = int(row["video_thumbnail_impressions"])
                # 2026-10-05修正: 従来は本編以外の動画（Shorts等）のインプレッションが混ざっていた
                if row["video_id"] in ep_map:
                    monthly_impr[ym] += impr
                else:
                    monthly_impr_other[ym] += impr
    for f in glob.glob(str(ANALYTICS_DIR / "channel_combined_a3" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                vid = row["video_id"]
                ym = row["date"][:6]
                combined_days[ym].add(row["date"])
                views = int(row["views"])
                engaged = int(row["engaged_views"])
                if vid in ep_map:
                    monthly[ym]["main_views"] += views
                    monthly[ym]["main_engaged"] += engaged
                elif vid in shorts_map:
                    monthly[ym]["shorts_views"] += views
                    monthly[ym]["shorts_engaged"] += engaged
                else:
                    monthly[ym]["other_views"] += views
                    monthly[ym]["other_engaged"] += engaged

    print("\n=== チャンネル全体 月次露出トレンド（本編のみ・1日あたりに正規化。Shorts/未登録は別掲） ===")
    print("  ⚠️ 2026-10-05: 7/11〜8/6にReporting APIのレポート欠損あり（combined 24日・reach 22日）。")
    print("     月の合計は日数が違うため比較に使わず、「日数」と「1日あたり」を見ること。")
    for ym in sorted(set(monthly_impr) | set(monthly)):
        impr = monthly_impr.get(ym, 0)
        m = monthly.get(ym, {})
        rd, cd = len(reach_days.get(ym, ())), len(combined_days.get(ym, ()))
        per_day_impr = impr / rd if rd else 0
        per_day_eng = m.get("main_engaged", 0) / cd if cd else 0
        print(f"  {ym[:4]}-{ym[4:]}: [reach{rd}日/combined{cd}日] "
              f"本編インプレ/日={per_day_impr:,.0f}(合計{impr:,})  "
              f"本編engaged視聴/日={per_day_eng:,.0f}(views={m.get('main_views',0):,}/engaged={m.get('main_engaged',0):,})  "
              f"Shorts視聴={m.get('shorts_views',0):,}(engaged={m.get('shorts_engaged',0):,})  "
              f"未登録視聴={m.get('other_views',0):,}  本編以外インプレ={monthly_impr_other.get(ym,0):,}")
    print("  ※ viewsはホームのインライン自動再生を含み視聴の質を表さない。判断にはengagedを使うこと（2026-10-05 Opus検証）。")


def print_acquisition_breakdown(min_engaged: int):
    """新規視聴者比率（非登録者視聴%）・流入経路別視聴を表示する（2026-09-06追加）。
    「新規視聴者獲得」の直接指標が意思決定に接続されていない問題（Fable監査M7）への対応。

    2026-09-28修正（Opus月次分析で発覚）: 従来はShorts・未登録動画のviewsが混在し、
    非登録者比率・流入経路の数字を歪めていた（例: 流入経路コード24＝24%はほぼ全量が
    Shorts由来）。本編（`youtube_url`が設定済みの動画）のengaged_viewsのみを対象にし、
    `subscribed_status=unknown`は分母から除外する。
    """
    acq = aggregate_acquisition()
    ep_map = build_episode_map()
    main_vids = set(ep_map.keys())

    total_engaged = sum(a["known_engaged"] for vid, a in acq.items() if vid in main_vids)
    total_unsub = sum(a["unsubscribed_engaged"] for vid, a in acq.items() if vid in main_vids)
    traffic_totals = defaultdict(int)
    for vid, a in acq.items():
        if vid not in main_vids:
            continue
        for src, v in a["traffic"].items():
            traffic_totals[src] += v
    total_traffic = sum(traffic_totals.values())

    print("\n=== 新規視聴者獲得・流入経路（本編のみ、engaged_views基準） ===")
    if total_engaged == 0:
        print("  データがありません")
        return
    print(f"  非登録者視聴（新規視聴者の代理指標、subscribed_status不明分は分母から除外）: "
          f"{total_unsub/total_engaged*100:.1f}%（対象engaged {total_engaged:,}件中）")
    print("  ※ 以下は全期間の累計。傾向は下の「月別」を見ること（累計は直近の変化を隠す）。")
    print("  流入経路別（累計、本編engaged_views基準。名称は公式ドキュメントの表による）:")
    for src, v in sorted(traffic_totals.items(), key=lambda x: -x[1]):
        pct = v / total_traffic * 100 if total_traffic else 0
        print(f"    {traffic_name(src)}: {pct:5.1f}%  ({v:,}件)")

    # 2026-10-14追加: 月別（本編のみ・engaged基準・1日あたり）。非登録者比率93.5%（累計）は、
    # 10月だけで見ると83%まで下がっている（登録者の視聴が急増）という変化を隠していた。
    mon = defaultdict(lambda: {"days": set(), "sub": 0, "ns": 0, "traffic": defaultdict(int)})
    for f in glob.glob(str(ANALYTICS_DIR / "channel_combined_a3" / "*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["video_id"] not in main_vids:
                    continue
                ym = row["date"][:6]
                mon[ym]["days"].add(row["date"])
                eng = int(row["engaged_views"])
                if row["subscribed_status"] == "subscribed":
                    mon[ym]["sub"] += eng
                elif row["subscribed_status"] == "not_subscribed":
                    mon[ym]["ns"] += eng
                mon[ym]["traffic"][row["traffic_source_type"]] += eng
    print("\n  月別（本編・engaged基準・1日あたり。月の日数が欠損で違うため合計でなく/日で比べる）:")
    for ym in sorted(mon):
        m = mon[ym]
        nd = len(m["days"])
        known = m["sub"] + m["ns"]
        tt = sum(m["traffic"].values())
        top = sorted(m["traffic"].items(), key=lambda x: -x[1])[:4]
        top_txt = " / ".join(f"{TRAFFIC_SOURCE_NAMES.get(c, 'code='+c)} {v/tt*100:.0f}%" for c, v in top) if tt else ""
        print(f"    {ym[:4]}-{ym[4:]}[{nd}日]: 登録者engaged/日={m['sub']/nd:5.1f}  非登録者engaged/日={m['ns']/nd:5.1f}  "
              f"非登録者比率={m['ns']/known*100 if known else 0:4.1f}%  流入上位: {top_txt}")

    print(f"\n  動画別 非登録者視聴%（本編、engaged>={min_engaged}のみ）:")
    rows = []
    for vid, a in acq.items():
        if vid not in main_vids or a["known_engaged"] < min_engaged:
            continue
        ep = ep_map.get(vid)
        pct = a["unsubscribed_engaged"] / a["known_engaged"] * 100 if a["known_engaged"] else 0
        rows.append((ep["episode_id"], a["known_engaged"], pct))
    if not rows:
        print(f"    該当なし（engaged>={min_engaged}を満たす動画がありません）")
        return
    for ep_id, engaged, pct in sorted(rows, key=lambda x: x[0]):
        print(f"    {ep_id}  engaged={engaged:5}  非登録者視聴={pct:5.1f}%")


def print_relative_category_breakdown(results: list):
    """タイトル型・登場人物数別を、月内相対CTR（14日窓・公開月中央値比）で比較し直す。

    2026-09-28追加（Opus月次分析対応）: `print_title_pattern_breakdown`等の
    累計値×impr閾値ベースの比較には2つの構造的バイアスがある。
    (1) impr1500+のような閾値フィルタは「露出」という結果変数（アルゴリズムが
        後から与えるもの）で選別しており、古い動画ほど残りやすい選択バイアスを持つ。
    (2) 累計CTRは新しい動画ほど不利/有利になる年齢バイアスを持つ。
    ここでは14日窓が完了した動画のみを対象に、各動画のCTRを「同じ公開月の
    中央値」との比較で評価する（コホート境界は公開月で固定し、事後的に動かさない）。
    **意思決定にはこちらを優先し、上記の累計値ベース集計は参考値として扱うこと。**
    """
    rows, _, _, _ = compute_age_adjusted_rows(results)
    if not rows:
        print("\n=== 月内相対CTR比較 ===\n  データ不足のため算出できません")
        return

    by_month = defaultdict(list)
    for row in rows:
        by_month[row["month"]].append(row["ctr"])
    # 2026-10-14修正: 従来は偶数nで「上側中央値」(sorted[n//2])を使っており通常の中央値と
    # ずれていた（8月: 2.08% vs 1.95%）。通常の中央値に統一する。
    month_median = {m: statistics.median(v) for m, v in by_month.items()}
    month_n = {m: len(v) for m, v in by_month.items()}

    def loo_ratio(row):
        """自分を除いた同月の中央値に対する比。中央値との二値比較（以上/未満）は、自分自身が
        中央値の計算に入るため値が反転しやすい（ep075が前回「未満」今回「以上」）。"""
        others = [r["ctr"] for r in rows if r["month"] == row["month"] and r is not row]
        if not others:
            return None
        med = statistics.median(others)
        return row["ctr"] / med if med > 0 else None

    for row in rows:
        row["ratio"] = loo_ratio(row)

    def boot_ci(vals, iters=2000, seed=20261014):
        """中央値の95%ブートストラップ信頼区間（動画を単位にリサンプリング。乱数は固定）。"""
        rng = random.Random(seed)
        meds = sorted(statistics.median(rng.choices(vals, k=len(vals))) for _ in range(iters))
        return meds[int(iters * 0.025)], meds[int(iters * 0.975)]

    ep_map_json = {}
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        ep_map_json[d.get("episode_id")] = d

    def category_report(keyfn, label):
        cat_rows = defaultdict(list)
        for row in rows:
            d = ep_map_json.get(row["episode_id"])
            if not d:
                continue
            key = keyfn(d)
            if key is None:
                continue
            cat_rows[key].append(row)
        print(f"\n=== {label}（月内相対CTR、14日窓完了分のみ、n<{MIN_BUCKET_N}は測定不能） ===")
        for key, items in sorted(cat_rows.items(), key=lambda x: -len(x[1])):
            if len(items) < MIN_BUCKET_N:
                print(f"  {key}: n={len(items)}  測定不能")
                continue
            ratios = [it["ratio"] for it in items if it["ratio"] is not None]
            pooled_impr = sum(it["impr"] for it in items)
            pooled_clicks = sum(it["clicks"] for it in items)
            pooled_ctr = pooled_clicks / pooled_impr * 100 if pooled_impr else 0
            months_used = sorted(set(it["month"] for it in items))
            if len(ratios) >= MIN_BUCKET_N:
                lo, hi = boot_ci(ratios)
                ratio_txt = (f"自己除外・同月中央値比の中央値={statistics.median(ratios):.2f}"
                             f"[95%CI {lo:.2f}〜{hi:.2f}]（1.00超が同月中央値より上）")
            else:
                ratio_txt = "中央値比は測定不能"
            print(f"  {key}: n={len(items)}  {ratio_txt}  "
                  f"プールCTR={pooled_clicks:.0f}/{pooled_impr:.0f}={pooled_ctr:.2f}%  "
                  f"(対象月: {','.join(months_used)})")

    category_report(lambda d: classify_title(title_for_classification(d)), "タイトル型別")

    def char_bucket(d):
        scenes = d.get("scenes", [])
        n_chars = len(set(s.get("character_ref") for s in scenes if s.get("character_ref")))
        return "1人" if n_chars <= 1 else ("2人" if n_chars == 2 else "3人以上")

    category_report(char_bucket, "登場人物数別")

    print(f"\n  （参考）公開月別サンプル数・14日CTR中央値: "
          + ", ".join(f"{m}(n={month_n[m]}, 中央値{month_median[m]:.2f}%)" for m in sorted(month_median)))

    # 2026-10-14追加: 公開月別の登録者比率と非登録者の視聴秒数（維持率の比較は非登録者に限る）。
    # 全視聴者の秒数は登録者比率の上昇で見かけ上伸びる（9月以降の「維持率改善」の主因）。
    print("\n=== 公開月別 14日窓の登録者比率・非登録者秒（中央値、非登録者engaged>=10の動画のみ秒を集計） ===")
    for m in sorted(by_month):
        mrows = [r for r in rows if r["month"] == m]
        srs = [r["sub_ratio"] for r in mrows if r["sub_ratio"] is not None]
        nss = [r["ns_sec"] for r in mrows if r["ns_sec"] is not None and r["ns_engaged14"] >= 10]
        sr_txt = f"登録者比率中央値={statistics.median(srs)*100:.0f}%" if srs else "登録者比率 n/a"
        ns_txt = (f"非登録者秒中央値={statistics.median(nss):.0f}秒(n={len(nss)})" if len(nss) >= 3
                  else f"非登録者秒 測定不能(n={len(nss)})")
        print(f"  {m[:4]}-{m[4:]}: 窓有効n={len(mrows)}  {sr_txt}  {ns_txt}")


def cli():
    if not GDRIVE_ROOT.exists():
        print(f"❌ Google Driveの同期フォルダが見つかりません: {GDRIVE_ROOT}")
        print("   Google Drive for desktopが起動・ログイン済みか確認してください。")
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Samurai Chronicles YouTube アナリティクス集計")
    parser.add_argument("--top", type=int, default=10, help="上位/下位表示件数（デフォルト10）")
    parser.add_argument("--min-impressions", type=int, default=1500,
                        help="CTR比較の最低インプレッション数（デフォルト1500。"
                             "2026-08-04改訂: 500だと実クリック15回程度で検出力不足のため引き上げ）")
    parser.add_argument("--min-views", "--min-engaged", dest="min_engaged", type=int, default=20,
                        help="維持率比較の最低engaged_views数（デフォルト20。2026-09-28改訂: "
                             "2026-08-27以降views水増しの影響でviews基準が実態を反映しなくなったため"
                             "engaged_views基準に切り替え、閾値もそれに合わせて50→20に引き下げ）")
    parser.add_argument("--full", action="store_true", help="全動画の一覧表も表示する")
    parser.add_argument("--no-age-adjusted", action="store_true",
                        help="公開後14日の年齢調整済み指標をスキップする")
    parser.add_argument("--no-monthly", action="store_true",
                        help="チャンネル全体の月次露出トレンドをスキップする")
    parser.add_argument("--no-acquisition", action="store_true",
                        help="新規視聴者獲得・流入経路の集計をスキップする（2026-09-06追加）")
    parser.add_argument("--no-relative", action="store_true",
                        help="月内相対CTRによるカテゴリ比較をスキップする（2026-09-28追加）")
    args = parser.parse_args()

    results = build_stats()
    if not results:
        print("❌ 集計対象データがありません。先に sc_yt_download_reports.py を実行してください。")
        return

    if args.full:
        print_main_table(results)
    print_top_bottom(results, args.top, args.min_impressions, args.min_engaged)
    print_title_pattern_breakdown(results, args.min_impressions, args.min_engaged)
    print_character_count_breakdown(results, args.min_impressions)
    if not args.no_age_adjusted:
        print_age_adjusted(results)
    if not args.no_relative:
        print_relative_category_breakdown(results)
    if not args.no_monthly:
        print_monthly_channel_summary()
    if not args.no_acquisition:
        print_acquisition_breakdown(args.min_engaged)


if __name__ == "__main__":
    cli()
