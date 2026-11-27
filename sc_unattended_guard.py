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


def file_fingerprint(path) -> str:
    """動画ファイルの SHA-256 の先頭16桁（承認の指紋）。"""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_approvals() -> list:
    """ポーラー（層A）が検証して渡す本人承認（#cc-inbox の user_approval）を読む。

    環境変数 HANDOFF_USER_APPROVAL（JSON。1件の dict か、その配列）:
        {"episode": "ep120", "sha256_16": "0123456789abcdef", "expires_at": "2026-11-28T12:00:00+09:00"}
    （2026-11-27 ユーザー決定。LW の3層ゲートと同じ考え方。形式は層A側と合わせること）
    """
    import json
    raw = os.environ.get("HANDOFF_USER_APPROVAL", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def require_user_approval(episode_id: str, video_path, episode: dict | None = None):
    """無人実行のとき、本人の承認がある場合に限り、その回1回だけアップロードを許可する（層B）。

    拒否: 承認なし／対象回が違う／指紋（動画の SHA-256 先頭16桁）が合わない／期限切れ／既にアップロード済み。
    対話実行（HANDOFF_UNATTENDED なし）には影響しない。--now は別途 forbid_unattended で常に拒否される。
    """
    if not is_unattended():
        return
    from datetime import datetime
    ep = _norm(episode_id)
    if episode and episode.get("youtube_url"):
        _refuse(f"{ep} は既にアップロード済みです（承認があっても再アップロードは不可）", always=True)
    mine = [a for a in _load_approvals() if _norm(str(a.get("episode", ""))) == ep]
    if not _load_approvals():
        _refuse(f"{ep}: 本人の承認（user_approval）がありません。最終動画の確認OK後に、#cc-inbox へ承認を出してください")
    if not mine:
        _refuse(f"{ep}: 承認の対象回が違います（承認があるのは: {', '.join(sorted({_norm(str(a.get('episode', ''))) for a in _load_approvals()}))}）")
    vp = os.fspath(video_path)
    if not os.path.exists(vp):
        _refuse(f"{ep}: 動画ファイルが見つからないため、承認の指紋を確認できません: {vp}")
    fp = file_fingerprint(vp)
    same = [a for a in mine if str(a.get("sha256_16", "")).strip().lower() == fp]
    if not same:
        _refuse(f"{ep}: 動画の指紋（{fp}）が承認と一致しません（確認後に動画が変わった可能性）")
    now = datetime.now().astimezone()
    for a in same:
        try:
            exp = datetime.fromisoformat(str(a.get("expires_at", "")))
            if exp.tzinfo is None:
                continue  # タイムゾーンなしは無効
            if now <= exp:
                return  # 承認OK
        except ValueError:
            continue
    _refuse(f"{ep}: 承認の有効期限が切れている（または期限の形式が不正です）")


def forbid_reupload(episode: dict, key: str, action: str = "再アップロード"):
    """無人実行のとき、すでにアップロード済みの回（episode[key] がある）への再アップロード・差し替えを拒否する。"""
    if is_unattended() and episode.get(key):
        _refuse(f"{action}（この回は既にアップロード済みです: {episode.get(key)}）", always=True)
