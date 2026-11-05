#!/usr/bin/env python3
"""
sc_unattended_guard.py — 無人実行（handoff-poller）でのアップロード系スクリプトの安全装置

handoff-poller は、無人実行の Claude を起動するとき環境変数 `HANDOFF_UNATTENDED=1` を渡す。
そのうえで、引き継ぎメモの**行頭**に次の形の行があるときだけ、その回に限って `HANDOFF_ALLOW_UPLOAD` を渡す
（LW の「即時公開: LW{NNN}」と同じ、機械的に判定できる形。2026-11-05、ユーザー決定）:

    アップロード指示: ep120
    アップロード指示：ep120 ep121      （複数回なら空白区切り）

アップロード系（sc_sns_up.py・learning/learn_upload.py・sc_playlist_manager.py・sc_build_site.py）は、
無人実行のとき、`HANDOFF_ALLOW_UPLOAD` に対象のエピソードが含まれていなければ何もせず終了する
（権限ルールの二重の備え。指示が無い場合は従来どおり実行されない）。
対話での実行（HANDOFF_UNATTENDED が無い）には何の影響もない。

--now（即時公開）・差し替え・削除・既存動画の書き換え・再アップロード・直近/過去の予約日時は、無人実行では指示があっても常に拒否する（SC では即時公開の運用を設けていない）。
"""
from __future__ import annotations

import os
import re
import sys


def _norm(s: str) -> str:
    m = re.search(r"(\d+)", s or "")
    return f"ep{int(m.group(1)):03d}" if m else (s or "").strip().lower()


def is_unattended() -> bool:
    return os.environ.get("HANDOFF_UNATTENDED") == "1"


def allowed_episodes() -> set:
    return {_norm(x) for x in re.split(r"[,\s]+", os.environ.get("HANDOFF_ALLOW_UPLOAD", "")) if x.strip()}


def _refuse(msg: str, always: bool = False):
    print(f"🚫 無人実行のため中止: {msg}", file=sys.stderr)
    if always:
        print("   この操作は、アップロード指示があっても無人では実行できません。実行せず、結果を「要確認」にして、人が行う手順を書いてください。", file=sys.stderr)
    else:
        print("   アップロード系は、メモの行頭に「アップロード指示: ep{NNN}」と明記された回だけ、その回に限って実行できます。"
              "指示が無い場合は実行せず、結果を「要確認」にしてください。", file=sys.stderr)
    sys.exit(1)


def require_upload_permission(episode_id: str | None, action: str = "アップロード"):
    """無人実行のとき、episode_id（None なら「どれか1回でも指示がある」）が許可されていなければ終了する。"""
    if not is_unattended():
        return
    allowed = allowed_episodes()
    if episode_id is None:
        if not allowed:
            _refuse(f"{action}（アップロード指示がありません）")
    elif _norm(episode_id) not in allowed:
        _refuse(f"{action}（{_norm(episode_id)} へのアップロード指示がありません。指示があるのは: {', '.join(sorted(allowed)) or 'なし'}）")


def forbid_unattended(action: str):
    """無人実行では、指示があっても常に拒否する操作（--now、削除など）。"""
    if is_unattended():
        _refuse(f"{action} は無人実行では実行できません", always=True)


def require_future_publish_at(publish_at: str | None, min_minutes: int = 10):
    """無人実行のとき、予約日時（JST、"YYYY-MM-DD HH:MM"）が今から min_minutes 分より先であることを要求する。
    過去や直近の日時は YouTube が即時公開にしてしまい、--now の禁止をすり抜けるため。None（自動スロット）は対象外。"""
    if not is_unattended() or not publish_at:
        return
    from datetime import datetime, timedelta, timezone
    jst = timezone(timedelta(hours=9))
    try:
        t = datetime.strptime(publish_at.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=jst)
    except ValueError:
        _refuse(f"予約日時の形式が読めません: {publish_at}（\"YYYY-MM-DD HH:MM\" の JST で指定）", always=True)
    if t < datetime.now(jst) + timedelta(minutes=min_minutes):
        _refuse(f"予約日時 {publish_at} は、今から{min_minutes}分以内か過去です（即時公開になるため、無人では実行できません）", always=True)


def forbid_reupload(episode: dict, key: str, action: str = "再アップロード"):
    """無人実行のとき、すでにアップロード済みの回（episode[key] がある）への再アップロード・差し替えを拒否する。"""
    if is_unattended() and episode.get(key):
        _refuse(f"{action}（この回は既にアップロード済みです: {episode.get(key)}）", always=True)
