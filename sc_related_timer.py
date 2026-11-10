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
制作専用 Chrome（2026-11-10 確定。LW の tools/lw-related-timer.sh と同じ方式）:
  ユーザーデータ ~/.lw-chrome-production（環境変数 HANDOFF_CHROME_UDD で変更可）で起動した Chrome の拡張（Claude in Chrome）だけを使う。
  deviceId は ~/.config/handoff-poller/repos.json の production_chrome.device_id。無ければ blocked（何も操作しない）。
  tools/handoff-chrome-guard.py（PreToolUse/PostToolUse フック）が、その deviceId を選べるまで他の操作を拒否し、navigate は
  studio.youtube.com・www.youtube.com に、javascript_tool は studio_related_video.js の実行だけに限る。
  Chrome は起動済みなら再起動も終了もしない。拡張は「ウィンドウが1つも無い」と接続しないため、無ければ背景に空ウィンドウを1つ開く。
環境変数:
  SC_RELATED_CLAUDE      claude コマンドのパス（既定 "claude"）
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
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
CHROME_UDD = Path(os.environ.get("HANDOFF_CHROME_UDD", str(Path.home() / ".lw-chrome-production")))
CHROME_HOSTS = "studio.youtube.com,www.youtube.com"
REPOS_JSON = Path.home() / ".config" / "handoff-poller" / "repos.json"
GUARD = ROOT / "tools" / "handoff-chrome-guard.py"
CHROME_STATE = LOG_DIR / "chrome-state"
CH_NAMES = {"sc": "Samurai Chronicles（@Samurai-Chronicles-JP、UCN1-TUxX_2UumGm3OKpmncg）",
            "learn": "英語で聴く日本史 / Samurai…（@eigo-de-nihonshi、UCWOFhTRNmbVeVWgwF9DfoNA）"}


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


SLACK_JSON_CANDIDATES = [Path.home() / ".config" / "handoff-poller" / "slack.json"]


def cc_reports_webhook() -> str:
    """slack.json の cc_reports_webhook_url（KL と同じ）。環境変数 SC_CC_REPORTS_WEBHOOK_URL があれば優先。"""
    if os.environ.get("SC_CC_REPORTS_WEBHOOK_URL"):
        return os.environ["SC_CC_REPORTS_WEBHOOK_URL"].strip()
    for p in [Path(os.environ["SC_SLACK_JSON"])] if os.environ.get("SC_SLACK_JSON") else SLACK_JSON_CANDIDATES:
        try:
            url = json.loads(p.read_text(encoding="utf-8")).get("cc_reports_webhook_url", "")
            if url:
                return str(url).strip()
        except Exception:
            continue
    return ""


def report_line(event: str, state: str, next_: str, needs_user: str) -> str:
    """常設監視が拾う1行形式（from=claude-code で始まる）。"""
    return (f"from=claude-code project=SC case=関連動画タイマー event={event} state={state} "
            f"next={next_} needs_user={needs_user}")


def report(text: str):
    """#cc-reports への報告（slack.json の cc_reports_webhook_url へ Incoming Webhook で投稿）。"""
    import urllib.request
    url = cc_reports_webhook()
    if not url:
        print("Slack 未投稿（cc_reports_webhook_url なし）:", text, file=sys.stderr)
        return
    body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            if res.status != 200:
                print(f"Slack 投稿が status={res.status}: {text}", file=sys.stderr)
    except Exception as exc:
        print(f"報告に失敗: {exc}: {text}", file=sys.stderr)


PROMPT = """これは無人の定期実行です。次の作業だけを行ってください。それ以外の操作はしません。

目的: YouTube Studio で、各ショートの「関連動画」に、同じ回の本編を設定する。
- ブラウザは制作専用 Chrome の1台だけ。最初に list_connected_browsers を呼び、deviceId {device} を select_browser で選ぶ。
  選んだあと list_connected_browsers で、そのブラウザが inUse になっていることを確かめる。選べない・inUse にならないときは
  何も操作せず RESULT {{"blocked":true,"note":"理由"}} で終える（普段使いのブラウザは選べない。ガードが拒否する）。
- 手順は `Read` で `.claude/commands/sc-upload.md` の STEP 3.5 手順4・5 と `studio_related_video.js` を読んで従う
  （スクリプトを localStorage に保存→各ショートの `studio.youtube.com/video/{{SHORTS_ID}}/edit` を開いて実行→読み込み直して確認→片付け）。
  操作は1つずつ（browser_batch は使えない）。座標クリックはチャンネル切替のメニュー操作だけに使う。
- チャンネルの切り替え: 対象の種別ごとに、先に正しいチャンネルへ切り替える。**URL を直接開いても切り替わらない**（権限エラーになる）。
  `studio.youtube.com/` を開き、右上のアバター → 「アカウントを切り替える」 → 一覧から次のチャンネルを選ぶ。切り替えたら
  アバターのメニューの先頭に表示されるチャンネル名で確かめる。違えばその回はスキップして報告する。
{chans}
  他チャンネルの動画は編集しない。種別が複数あるときは、1種別を終えてから次の種別へ切り替える。
- 終わったら（結果がどうでも）、この実行で自分が開いた Studio のタブを tabs_close_mcp で閉じる。他のタブ・about:blank は閉じない。
  （実行が終わるとタブが残り、次の実行からは閉じられないため。2026-11-11）
- アップロード・公開・予約公開・タイトル・説明・字幕・コメントなど、関連動画以外は一切変更しない。
- リンク先は「ショート → 同じ回の本編」固定。検索語は下の表のものをそのまま使う。判断で変えない。
- 保存後に読み込み直し、関連動画欄が本編のタイトルになっていることを確かめた回だけ verified:true とする。完了の記録（--mark）はこのスクリプト側が行うので、あなたは書かない。
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


def prod_device_id() -> str:
    try:
        return str(json.loads(REPOS_JSON.read_text(encoding="utf-8")).get("production_chrome", {}).get("device_id", "") or "")
    except Exception:
        return ""


def chrome_pid() -> int:
    try:
        pid = int(os.readlink(CHROME_UDD / "SingletonLock").rsplit("-", 1)[1])
        os.kill(pid, 0)
        return pid
    except Exception:
        return 0


def chrome_ext_up() -> bool:
    pid = chrome_pid()
    if not pid:
        return False
    out = subprocess.run(["ps", "-eo", "ppid=,command="], capture_output=True, text=True).stdout
    return any(l.split(None, 1)[0] == str(pid) and "--chrome-native-host" in l for l in out.splitlines() if l.strip())


def ensure_chrome() -> str:
    """制作専用 Chrome を操作できる状態にする。できなければ理由（blocked 用）を返す。起動済みなら再起動も終了もしない。"""
    base = ["open", "-g", "-na", "Google Chrome", "--args", f"--user-data-dir={CHROME_UDD}",
            "--no-first-run", "--no-default-browser-check"]
    if not chrome_pid():
        subprocess.run(base + ["about:blank"], check=False)
        time.sleep(5)
    elif not chrome_ext_up():
        subprocess.run(base + ["about:blank"], check=False)   # ウィンドウが無いと拡張が接続しない（2026-11-10 実機確認）
    for _ in range(30):
        if chrome_ext_up():
            return ""
        time.sleep(3)
    return "制作専用 Chrome の拡張機能（Claude in Chrome）が90秒待っても接続しない"


def run_claude(rows: list, device_id: str) -> tuple:
    claude = os.environ.get("SC_RELATED_CLAUDE", "claude")
    table = "\n".join(f"- {r['kind']} {r['episode_id']} shorts={r['shorts_id']} 本編={r['main_id']} 検索語「{r['search']}」"
                      for r in rows)
    chans = "\n".join(f"  - {k}: {CH_NAMES[k]}" for k in sorted({r["kind"] for r in rows}))
    prompt = PROMPT.format(chans=chans, rows=table, device=device_id)
    CHROME_STATE.mkdir(parents=True, exist_ok=True)
    cm = "mcp__claude-in-chrome__"
    settings = CHROME_STATE / "settings-sc-related.json"
    hook = f"python3 -I {GUARD}"
    settings.write_text(json.dumps({"hooks": {
        "PreToolUse": [{"matcher": cm + ".*", "hooks": [{"type": "command", "command": hook, "timeout": 10}]}],
        "PostToolUse": [{"matcher": cm + "(select_browser|list_connected_browsers)",
                         "hooks": [{"type": "command", "command": hook + " post", "timeout": 10}]}]}}), encoding="utf-8")
    allowed = ["Read"] + [cm + t for t in ("list_connected_browsers", "select_browser", "tabs_context_mcp", "tabs_create_mcp",
                                           "navigate", "computer", "read_page", "find", "get_page_text", "javascript_tool", "tabs_close_mcp")]
    denied = ["Bash", "Write", "Edit", "Agent", "WebFetch", "WebSearch"] + [cm + t for t in (
        "read_network_requests", "read_console_messages", "browser_batch", "switch_browser", "gif_creator",
        "upload_image", "resize_window", "file_upload", "form_input")]
    env = dict(os.environ, HANDOFF_CHROME_DEVICE_ID=device_id, HANDOFF_CHROME_HOSTS=CHROME_HOSTS,
               HANDOFF_CHROME_STATE_DIR=str(CHROME_STATE), HANDOFF_UNATTENDED="1")
    cmd = [claude, "-p", prompt, "--model", "sonnet", "--permission-mode", "default",
           "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
           "--tools", "Read", "--chrome", "--settings", str(settings),
           "--allowedTools", *allowed, "--disallowedTools", *denied]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return set(), {}, "タイムアウト"
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
        elif not prod_device_id():
            blocked_now = f"制作専用ブラウザの device_id が設定に無い（{REPOS_JSON} の production_chrome.device_id）"
        elif (why := ensure_chrome()):
            blocked_now = why
        elif screen_locked():
            blocked_now = "画面ロック中のため Studio を操作できません"
        else:
            done, fail, blocked_now = run_claude(rows, prod_device_id())
            ok = [r for r in rows if key(r) in done]
            for r in ok:
                mark_done(r)
            if ok:
                names = "、".join(f"{r['episode_id']}({'学習版' if r['kind']=='learn' else '本編'})" for r in ok)
                report(report_line(f"関連動画を設定: {names}", "done", "なし", "no"))
                st.pop("blocked_reported", None)
            if fail:
                print("未完了（次回再試行）:", fail, file=sys.stderr)
                fk = ",".join(sorted(fail))
                if st.get("fail_reported") != fk:   # 同じ失敗の組は1回だけ報告
                    report(report_line("関連動画の設定に失敗: " + "; ".join(f"{k}={v}"[:80] for k, v in fail.items()),
                                       "failed", "15分ごとに自動再試行", "no（続く場合は要確認）"))
                    st["fail_reported"] = fk
            else:
                st.pop("fail_reported", None)
        if blocked_now:
            if not st.get("blocked_reported"):   # blocked は連続中1回だけ報告（再試行は続ける）
                report(report_line(f"blocked: {blocked_now}（対象{len(rows)}件は未設定）", "blocked",
                                   "15分ごとに自動再試行", "no（続く場合は制作専用Chromeの状態を確認）"))
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
