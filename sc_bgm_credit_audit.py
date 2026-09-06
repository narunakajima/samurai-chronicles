"""
sc_bgm_credit_audit.py — CC BY BGMクレジットの欠落を検出・修正する（Fable監査対応）

背景: sc_bgm_library.py の --use-library は CC BY 曲の credit.txt を /tmp に用意し、
sc-new.md STEP 4 のシェルシーケンスが sc_inject_bgm_credit.py を呼んで
episodes/ep{NNN}.json の youtube_description に注入する設計になっている。
しかし ep050/065/070/079/080/089 の6話でこの注入が行われておらず
（ep050は旧形式の単曲bgm_source、他は3曲構成でも何らかの理由でこの経路を通らなかった）、
概要欄のクレジット欠落が発生していた（2026-09-07 Fable監査で発覚）。

このスクリプトは全エピソードを対象に、bgm_source/bgm_sources が参照する
bgm_library.json のエントリを解決し、CC BY かつ credit 未記載のものを検出する。

使い方:
  python3 sc_bgm_credit_audit.py                 # 検出のみ（何も変更しない）
  python3 sc_bgm_credit_audit.py --fix           # ローカルの episodes/ep{NNN}.json に
                                                  # クレジットを追記する（YouTubeへの反映は別途）
  python3 sc_bgm_credit_audit.py --fix --push    # 追記に加え、youtube_url が設定済み
                                                  # （＝公開済み）の動画は videos.update で
                                                  # 概要欄を実際に更新する
"""

import argparse
import glob
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
BGM_LIBRARY_JSON = BASE_DIR / "bgm_library.json"


def _load_library_by_path() -> dict:
    library = json.loads(BGM_LIBRARY_JSON.read_text(encoding="utf-8"))
    return {entry["path"]: entry for entry in library}


def _resolve_bgm_sources(ep: dict) -> list:
    """episode JSONのbgm_source(単曲・旧形式)/bgm_sources(role別)を
    bgm_library.jsonのパスキーのリストとして返す。"""
    sources = []
    if ep.get("bgm_source"):
        sources.append(ep["bgm_source"])
    if ep.get("bgm_sources"):
        sources.extend(v for v in ep["bgm_sources"].values() if v)
    return sources


def audit() -> list:
    """欠落しているエピソードのリストを返す。
    各要素: {"episode_id", "missing_credits": [credit_line, ...], "published": bool}
    """
    lib_by_path = _load_library_by_path()
    results = []
    for f in sorted(glob.glob(str(BASE_DIR / "episodes" / "ep*.json"))):
        ep = json.loads(Path(f).read_text(encoding="utf-8"))
        desc = ep.get("youtube_description", "")
        missing = []
        for path in _resolve_bgm_sources(ep):
            entry = lib_by_path.get(path)
            if not entry:
                continue  # 旧パス形式でbgm_library.jsonと一致しないケース（別途要確認）
            if entry.get("license") == "CC BY" and entry.get("credit"):
                credit_line = entry["credit"]
                if credit_line not in desc:
                    if credit_line not in missing:
                        missing.append(credit_line)
        if missing:
            results.append({
                "episode_id": ep.get("episode_id"),
                "missing_credits": missing,
                "published": bool(ep.get("youtube_url")),
                "youtube_url": ep.get("youtube_url"),
            })
    return results


def _inject(ep: dict, credit_lines: list) -> dict:
    desc = ep.get("youtube_description", "")
    for credit_line in credit_lines:
        if credit_line in desc:
            continue
        hashtag_idx = desc.find("\n#")
        if hashtag_idx != -1:
            desc = desc[:hashtag_idx] + f"\n\n{credit_line}" + desc[hashtag_idx:]
        else:
            desc = desc.rstrip() + f"\n\n{credit_line}"
    ep["youtube_description"] = desc
    return ep


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="ローカルのepisode JSONに追記する")
    parser.add_argument("--push", action="store_true",
                        help="--fixと併用。公開済み動画はvideos.updateで概要欄を実際に更新する")
    args = parser.parse_args()

    results = audit()
    if not results:
        print("✅ クレジット欠落は検出されませんでした。")
        return

    print(f"⚠️ クレジット欠落を{len(results)}話で検出:\n")
    for r in results:
        print(f"  {r['episode_id']}（{'公開済み' if r['published'] else '未公開'}）:")
        for c in r["missing_credits"]:
            print(f"    + {c}")

    if not args.fix:
        print("\n--fix なしのため変更は行いません。")
        return

    for r in results:
        ep_json = BASE_DIR / "episodes" / f"{r['episode_id']}.json"
        ep = json.loads(ep_json.read_text(encoding="utf-8"))
        ep = _inject(ep, r["missing_credits"])
        ep_json.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ {r['episode_id']}: episodes/{r['episode_id']}.json に追記しました")

    if not args.push:
        print("\n公開済み動画の概要欄はまだ更新されていません。"
              "--push を付けて再実行するとYouTube側にも反映します。")
        return

    from sc_sns_up import get_youtube_client
    youtube = get_youtube_client()
    for r in results:
        if not r["published"]:
            continue
        video_id = r["youtube_url"].rstrip("/").split("/")[-1]
        ep_json = BASE_DIR / "episodes" / f"{r['episode_id']}.json"
        ep = json.loads(ep_json.read_text(encoding="utf-8"))
        try:
            youtube.videos().update(
                part="snippet",
                body={
                    "id": video_id,
                    "snippet": {
                        "title": ep["youtube_title"],
                        "description": ep["youtube_description"],
                        "tags": ep.get("youtube_tags", []),
                        "categoryId": "27",
                    },
                },
            ).execute()
            print(f"  ✓ {r['episode_id']} ({video_id}): YouTube概要欄を更新しました")
        except Exception as e:
            print(f"  ⚠️ {r['episode_id']} ({video_id}): 更新失敗 — {e}")


if __name__ == "__main__":
    main()
