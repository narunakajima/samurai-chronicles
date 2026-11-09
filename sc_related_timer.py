#!/usr/bin/env python3
"""
sc_related_timer.py — ショート関連動画（同じ回の本編）の自動設定タイマー（2026-11-10 ユーザー承認の仕様）

launchd が15分間隔で `python3 sc_related_timer.py run` を呼ぶ。対象があるときだけ、制作専用 Chrome の
YouTube Studio で、ショートの「関連動画」に同じ回の本編を設定する。

対象（既存の抽出をそのまま使う。判断は足さない）:
  SC 本編側 : sc_related_targets.targets()      （scheduled_at を過ぎ、related_video_set が未設定）
  学習版    : learning/learn_targets.targets()["related"]  （publish_at を過ぎ、related_video_set が未設定）

境界（厳守）:
  - アップロード・公開・予約公開の変更はしない。関連動画以外の Studio 操作・設定変更・コメント返信もしない。
  - リンク先は「ショート → 同じ回の本編」で固定（検索語も既存の抽出が出したものだけ）。
  - 完了の記録は、画面で本編タイトルになったことを確かめた回だけ（SC: episodes/ep*.json、学習版: learning/uploads/*.json）。
  - 失敗は未設定のまま残し、次のチェックで再試行する。画面ロック等は blocked として1回だけ報告する（再試行は続ける）。

使い方:
  python3 sc_related_timer.py dry-run      # 対象の抽出だけ（Studio 操作・記録・報告なし）
  python3 sc_related_timer.py run          # launchd が呼ぶ本番
  python3 sc_related_timer.py plist        # launchd 用 plist を標準出力に出す（登録はユーザーが行う）
環境変数:
  SC_RELATED_CHROME_APP  制作専用 Chrome のアプリ名（既定 "Google Chrome"）
  SC_RELATED_CLAUDE      claude コマンドのパス（既定 "claude"）
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "learning"))
import sc_related_targets as sc_t          # noqa: E402
import learn_targets as lr_t               # noqa: E402

JST = timezone(timedelta(hours=9))
LABEL = "com.naru.sc-related-timer"
LOG_DIR = Path.home() / "Library" / "Logs" / "claude-team"
STATE = LOG_DIR / "sc-related-timer-state.json"   # リポジトリ外（未コミット変更で git pull を止めない）
LOCK = Path("/tmp/sc_related_timer.lock")
CHANNEL_SC = "UCN1-TUxX_2UumGm3OKpmncg"
RUN_TIMEOUT = 20 * 60


def collect(now: datetime) -> list:
    """SC 本編側・学習版の対象を、同じ形の行にそろえる。"""
    rows = []
    for r in sc_t.targets(now):
        rows.append({"kind": "sc", "episode_id": r["episode_id"], "shorts_id": r["shorts_id"],
                     "main_id": r["main_id"], "search": r["search"], "title": r["title"]})
    for r in lr_t.targets(now)["related"]:
        rows.append({"kind": "learn", "episode_id": r["episode_id"], "shorts_id": r["shorts_id"],
                     "main_id": r["main_id"], "search": r["search"], "title": r["search"]})
    return rows


def key(r: dict) -> str:
    return f"{r['kind']}:{r['episode_id']}"


def mark_done(r: dict):
    """既存の記録方法と同じ内容を直接書く（CLI の --mark/--mark-related と同じ結果）。"""
    if r["kind"] == "sc":
        for path, ep in sc_t.load_all():
            if ep.get("episode_id") == r["episode_id"] and not ep.get("related_video_set"):
                ep["related_video_set"] = True
                path.write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        rec = lr_t.load_rec(r["episode_id"])
        if rec.get("short_id"):
            rec["related_video_set"] = True
            lr_t.save_rec(r["episode_id"], rec)


def screen_locked() -> bool:
    out = subprocess.run(["ioreg", "-n", "Root", "-d1"], capture_output=True, text=True).stdout
    return '"CGSSessionScreenIsLocked"=Yes' in out.replace(" ", "")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def report(text: str):
    """#cc-reports への報告（既存の team_scheduled.post_slack = Incoming Webhook を共用）。"""
    try:
        import team_scheduled
        if not team_scheduled.post_slack(text):
            print("Slack 未投稿（Webhook なし／失敗）:", text, file=sys.stderr)
    except Exception as exc:
        print(f"報告に失敗: {exc}: {text}", file=sys.stderr)


PROMPT = """これは無人の定期実行です。次の作業だけを行ってください。それ以外の操作はしません。

目的: YouTube Studio で、各ショートの「関連動画」に、同じ回の本編を設定する。
- 使うのは Claude in Chrome（制作専用 Chrome）だけ。リポジトリの `studio_related_video.js` と
  `.claude/commands/sc-upload.md` の STEP 3.5 手順4・5（スクリプトを localStorage に保存→各ショートの
  `studio.youtube.com/video/{{SHORTS_ID}}/edit` で実行→読み込み直して確認→片付け）に従う。
- 種別 sc は SC チャンネル（{ch}）、種別 learn は学習版チャンネルで操作する。チャンネルが違えば
  その回はスキップして報告する。他チャンネルの動画は編集しない。
- アップロード・公開・予約公開・タイトル・説明・字幕・コメントなど、関連動画以外は一切変更しない。
- リンク先は「ショート → 同じ回の本編」固定。検索語は下の表のものをそのまま使う。判断で変えない。
- 保存後に読み込み直し、関連動画欄が本編のタイトルになっていることを確かめた回だけ verified:true とする。
- 画面ロック・ログイン切れ・権限なし・拡張未接続などで進めないときは、無理せず blocked:true で終える。

対象:
{rows}

最後の出力は、1回につき1行の次の形式の JSON 行だけを必ず出す（他の説明は後ろに付けてよい）:
RESULT {{"kind":"sc","episode_id":"ep118","verified":true,"note":""}}
失敗は verified:false と note に理由。全体が進めない場合は RESULT {{"blocked":true,"note":"理由"}} を1行。
"""


def parse_results(text: str) -> tuple:
    done, fail, blocked = set(), {}, ""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("RESULT "):
            continue
        try:
            j = json.loads(line[7:])
        except ValueError:
            continue
        if j.get("blocked"):
            blocked = j.get("note", "blocked")
        elif j.get("verified") is True:
            done.add(f"{j.get('kind')}:{j.get('episode_id')}")
        else:
            fail[f"{j.get('kind')}:{j.get('episode_id')}"] = j.get("note", "")
    return done, fail, blocked


def run_claude(rows: list) -> tuple:
    claude = os.environ.get("SC_RELATED_CLAUDE", "claude")
    app = os.environ.get("SC_RELATED_CHROME_APP", "Google Chrome")
    subprocess.run(["open", "-a", app], check=False)
    table = "\n".join(f"- {r['kind']} {r['episode_id']} shorts={r['shorts_id']} 本編={r['main_id']} 検索語「{r['search']}」"
                      for r in rows)
    prompt = PROMPT.format(ch=CHANNEL_SC, rows=table)
    cmd = [claude, "-p", prompt, "--model", "sonnet",
           "--allowedTools", "mcp__claude-in-chrome__*,Read,ToolSearch"]
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        return set(), {}, "タイムアウト"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"sc-related-timer-{datetime.now(JST):%Y%m%d-%H%M}.log").write_text(p.stdout + "\n" + p.stderr, encoding="utf-8")
    return parse_results(p.stdout)


def cmd_dry_run():
    now = datetime.now(JST)
    rows = collect(now)
    print(f"[dry-run] {now:%Y-%m-%d %H:%M} JST  対象 {len(rows)}件（Studio 操作・記録・報告なし）")
    for r in rows:
        print(f"  {r['kind']:5} {r['episode_id']}  shorts={r['shorts_id']}  本編={r['main_id']}  検索語「{r['search']}」")


def cmd_run():
    LOCK.touch()
    with open(LOCK, "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return   # 前回がまだ実行中
        now = datetime.now(JST)
        rows = collect(now)
        if not rows:
            return
        st = load_state()
        blocked_now = ""
        if screen_locked():
            blocked_now = "画面ロック中のため Studio を操作できません"
        else:
            done, fail, blocked_now = run_claude(rows)
            ok = [r for r in rows if key(r) in done]
            for r in ok:
                mark_done(r)
            if ok:
                report("【SC関連動画の自動設定】完了: " + "、".join(f"{r['episode_id']}({'学習版' if r['kind']=='learn' else '本編'})" for r in ok))
                st.pop("blocked_reported", None)
            if fail:
                print("未完了（次回再試行）:", fail, file=sys.stderr)
        if blocked_now:
            if not st.get("blocked_reported"):   # blocked は連続中1回だけ報告（再試行は続ける）
                report(f"【SC関連動画の自動設定】blocked: {blocked_now}（対象 {len(rows)}件は未設定のまま、15分ごとに再試行します）")
                st["blocked_reported"] = now.isoformat()
        save_state(st)


def cmd_plist():
    import plistlib
    d = {"Label": LABEL, "ProgramArguments": ["/usr/bin/python3", str(ROOT / "sc_related_timer.py"), "run"],
         "WorkingDirectory": str(ROOT), "StartInterval": 900, "RunAtLoad": False,
         "StandardOutPath": str(LOG_DIR / "sc-related-timer.out"), "StandardErrorPath": str(LOG_DIR / "sc-related-timer.err"),
         "EnvironmentVariables": {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"}}
    sys.stdout.write(plistlib.dumps(d).decode())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["dry-run", "run", "plist"])
    a = ap.parse_args()
    {"dry-run": cmd_dry_run, "run": cmd_run, "plist": cmd_plist}[a.command]()


if __name__ == "__main__":
    main()
