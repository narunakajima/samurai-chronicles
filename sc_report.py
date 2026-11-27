#!/usr/bin/env python3
"""sc_report.py — 工程の締め（Slack報告の文面づくり＋状態の記録＋チームログ）を1つの操作にする。
KL の kl_report.py を3プロジェクト共通化で移植したもの（2026-11-19、なるさん承認）。

背景（2026-11-19、kl059）: 報告の漏れ・「次は〇〇」と書いて応答を終える停止・承認の結果ファイルの読み忘れが続いた。
決まりを文章で書くだけでは守られないため、(1) 報告の文面を毎回この形で作る、(2) 「何を報告したか・次に何をするか・
何を待っているか」を状態ファイルに残す、(3) 応答を終えるとき sc_stop_check.py（Stop フック）がその状態を確かめる、
という形にした（編集長ケビンの提案を、なるさんが2026-11-19に承認）。

Slack への投稿そのものは、セッションの Slack ツール（スレッドに返信できる）で行う。このスクリプトは投稿しない
（webhook はスレッドに返信できず、スレッドを分けてしまうため）。出力された1行を、そのまま投稿する。

使い方:
  python3 sc_report.py start  --case ep131
      制作の開始。状態を初期化する（thread_ts は --thread-ts で渡すと記録）。
  python3 sc_report.py step   --case ep131 --step "8 音声生成" --by ダニエル --next "STEP9 テロップ" \
        [--state ok] [--eta 20分] [--needs-user なし] [--ref パス] [--note "結果: …"] \
        [--waiting none|bg|agent|approval] [--log-agent kl-coordinator --log-result ok]
      step_done の1行を表示し、状態に「報告済み・次の工程・待ち」を記録する。--log-agent を付けると
      team_log.py add も同時に実行する（報告と記録を1つの操作に）。
      --waiting は、応答を終えたあと何を待つか。none（既定）は「次の工程を今すぐ実行する」の意味で、
      この状態で応答を終えようとすると Stop フックが止める。
  python3 sc_report.py decision --case ep131 --step "12 完成動画の確認" --needs-user "…" [--ref …]
      needs_decision の1行を表示し、状態を waiting=approval にする（承認待ちで止まってよい）。
  python3 sc_report.py consumed --case ep131
      承認の結果ファイルを読んで取り込んだ印を付ける（Stop フックの「未読の承認あり」を解除）。
  python3 sc_report.py done   --case ep131
      案件の完成。状態を閉じる（以後 Stop フックは何も止めない）。
  python3 sc_report.py show
      現在の状態を表示する。
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "team" / "session_state.json"


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(d):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    d["updated_at"] = time.time()
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def line(case, event, step, by, state, nxt, eta, needs_user, ref):
    return (f"from=claude-code / project=SC / case={case} / event={event} / step={step} / by={by} / "
            f"state={state} / next={nxt} / eta={eta} / needs_user={needs_user} / ref={ref}")


# アップロードの失敗・警告は #cc-reports へ送る（2026-11-28、案件 2026-11-27-004。ユーザー承認）。
# team_scheduled.py の slack_webhook_team_reports_*.txt（月次評価の向き先）とは分ける。
# 専用ファイルが無ければ、ポーラーが #cc-reports への投稿に使う Webhook を使う。
SLACK_WEBHOOK_FILE = "~/.claude/secrets/slack_webhook_upload_failure_samurai-chronicles.txt"
POLLER_SLACK_JSON = "~/.config/handoff-poller/slack.json"
ALERT_LOG_DIR = ROOT / "team" / "upload_alerts"


def _slack_webhook() -> str:
    """失敗・警告の報告用（#cc-reports 向け）の Incoming Webhook URL。無ければ空文字（記録ファイルのみ）。"""
    import os
    if os.environ.get("TEAM_SLACK_WEBHOOK"):
        return os.environ["TEAM_SLACK_WEBHOOK"].strip()
    p = Path(os.path.expanduser(SLACK_WEBHOOK_FILE))
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    poller = Path(os.path.expanduser(POLLER_SLACK_JSON))
    if poller.exists():
        try:
            return str(json.loads(poller.read_text(encoding="utf-8")).get("cc_reports_webhook_url", "")).strip()
        except (OSError, ValueError):
            pass
    return ""


def build_alert(case, failures, warnings):
    """失敗・警告の一覧を、#cc-reports 向けの文面にする。"""
    head = "❌" if failures else "⚠️"
    msg = f"{head} *SC アップロード {case}*: 失敗 {len(failures)} 件・警告 {len(warnings)} 件"
    if failures:
        msg += "\n*失敗*\n" + "\n".join(f"• {x}" for x in failures)
    if warnings:
        msg += "\n*警告（処理は続行）*\n" + "\n".join(f"• {x}" for x in warnings)
    return msg


def post_alert(case, failures, warnings, dry_run=False):
    """失敗・警告があれば #cc-reports へ送る（Incoming Webhook）。何もなければ送らない。
    Webhook 未設定・送信失敗でも例外は出さず、team/upload_alerts/{case}.txt に必ず残す。戻り値は 送信できたか。"""
    if not failures and not warnings:
        return False
    msg = build_alert(case, failures, warnings)
    if dry_run:
        print("[dry-run] 送信予定の文面:\n" + msg)
        return False
    try:
        ALERT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(ALERT_LOG_DIR / f"{case}.txt", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + msg + "\n\n")
    except Exception as e:
        print(f"⚠ 失敗・警告の記録ファイルを書けません: {e}", file=sys.stderr)
    url = _slack_webhook()
    if not url:
        print("⚠ Slack の Webhook が未設定のため通知できません（記録ファイルのみ）", file=sys.stderr)
        return False
    try:
        import urllib.request
        body = json.dumps({"text": msg[:39000]}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status == 200
    except Exception as e:
        print(f"⚠ Slack への通知に失敗: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--case", required=True); p.add_argument("--thread-ts", default="")
    p = sub.add_parser("step")
    p.add_argument("--case", required=True); p.add_argument("--step", required=True)
    p.add_argument("--by", default="トーマス"); p.add_argument("--next", dest="nxt", required=True)
    p.add_argument("--state", default="ok"); p.add_argument("--eta", default="-")
    p.add_argument("--needs-user", default="なし"); p.add_argument("--ref", default="なし")
    p.add_argument("--note", default="")
    p.add_argument("--waiting", choices=["none", "bg", "agent", "approval"], default="none")
    p.add_argument("--log-agent", default=""); p.add_argument("--log-result", default="ok")
    p = sub.add_parser("decision")
    p.add_argument("--case", required=True); p.add_argument("--step", required=True)
    p.add_argument("--by", default="トーマス"); p.add_argument("--needs-user", required=True)
    p.add_argument("--ref", default="なし"); p.add_argument("--note", default="")
    p = sub.add_parser("consumed"); p.add_argument("--case", required=True)
    p = sub.add_parser("done"); p.add_argument("--case", required=True)
    sub.add_parser("show")
    p = sub.add_parser("alert")  # 動作確認用: 失敗・警告の通知文面を表示（--dry-run）または送信
    p.add_argument("--case", required=True)
    p.add_argument("--fail", action="append", default=[]); p.add_argument("--warn", action="append", default=[])
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.cmd == "alert":
        return 0 if post_alert(a.case, a.fail, a.warn, dry_run=a.dry_run) or a.dry_run else 1

    if a.cmd == "show":
        print(json.dumps(load(), ensure_ascii=False, indent=2))
        return 0

    s = load()
    if a.cmd == "start":
        s = {"active_case": a.case, "thread_ts": a.thread_ts, "waiting": "none", "pending_next": "",
             "last_step": "開始", "last_reported_at": time.time(), "approval_consumed_at": time.time()}
        save(s)
        print(f"状態を開始: {a.case}")
        return 0

    if s.get("active_case") not in (None, "", a.case) and a.cmd != "done":
        print(f"⚠ 状態の案件は {s.get('active_case')} です。{a.case} に切り替えます", file=sys.stderr)
    s["active_case"] = a.case

    if a.cmd == "step":
        msg = line(a.case, "step_done", a.step, a.by, a.state, a.nxt, a.eta, a.needs_user, a.ref)
        if a.note:
            msg += "\n" + a.note
        s.update({"last_step": a.step, "last_reported_at": time.time(), "pending_next": a.nxt,
                  "waiting": a.waiting})
        save(s)
        if a.log_agent:
            subprocess.run([sys.executable, str(ROOT / "team_log.py"), "add", "--agent", a.log_agent,
                            "--episode", a.case, "--step", a.step, "--result", a.log_result],
                           cwd=str(ROOT), check=False)
        print("▼ これを #cc-reports の案件スレッドに投稿し、あわせて #cc-inbox を読むこと")
        print(msg)
        if a.waiting == "none":
            print(f"▼ 次の工程「{a.nxt}」を、この応答の中で今すぐ実行すること（書いて終えない）")
        return 0

    if a.cmd == "decision":
        msg = line(a.case, "needs_decision", a.step, a.by, "判断待ち", "ご回答後に反映", "-", a.needs_user, a.ref)
        if a.note:
            msg += "\n" + a.note
        s.update({"last_step": a.step, "last_reported_at": time.time(), "pending_next": "承認待ち",
                  "waiting": "approval", "decision_posted_at": time.time()})
        save(s)
        print("▼ これを #cc-reports の案件スレッドに投稿 → 承認の監視（approval-watch.py）を起動 → その完了通知を待つ")
        print(msg)
        return 0

    if a.cmd == "consumed":
        s.update({"approval_consumed_at": time.time(), "waiting": "none"})
        save(s)
        print("承認を取り込み済みにしました（次の工程を実行すること）")
        return 0

    if a.cmd == "done":
        msg = line(a.case, "done", "完了", "トーマス", "ok", "公開日に公開", "-", "なし", "なし")
        save({"active_case": "", "waiting": "none", "pending_next": "", "last_step": "完了",
              "last_reported_at": time.time(), "approval_consumed_at": time.time()})
        print("▼ done を #cc-reports に投稿すること（本文に結果を書く）")
        print(msg)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

