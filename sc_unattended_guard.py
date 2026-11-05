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

--now（即時公開）と、動画を削除する操作は、無人実行では指示があっても常に拒否する（SC では即時公開の運用を設けていない）。
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


def _refuse(msg: str):
    print(f"🚫 無人実行のため中止: {msg}", file=sys.stderr)
    print("   アップロードは、メモの行頭に「アップロード指示: ep{NNN}」と明記された回だけ、その回に限って実行できます。"
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
        _refuse(f"{action} は無人実行では実行できません")
