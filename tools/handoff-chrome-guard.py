#!/usr/bin/env python3 -I
# -*- coding: utf-8 -*-
"""handoff-chrome-guard.py — ポーラーの無人実行で Claude in Chrome を使うときの PreToolUse ガード。

ポーラーが `--settings` で渡すフック設定から呼ばれる（設定ファイルは実行ごとに生成。リポジトリの設定は読まない）。
権限ルールではツールごとの許可しか書けないため、次をここで強制する:
  1. 制作専用ブラウザ（環境変数 HANDOFF_CHROME_DEVICE_ID の deviceId）を select_browser で選んで「成功」するまで、他のブラウザ操作を拒否する。
     選んでよいのはその deviceId だけ（普段使いのブラウザは選べない）。「選択済み」の印は PostToolUse（ツールが成功したときだけ発火する）で立てる。
     list_connected_browsers の結果で、使用中（inUse）のブラウザが制作専用でない、または制作専用が見えないときは印を消す。
     （選択に失敗しても印が立つと、既定の普段使いブラウザに操作が流れるため。2026-11-05 のプローブで見つけた穴）
     使い方: 引数なし=PreToolUse、引数 post=PostToolUse。
  2. navigate は、HANDOFF_CHROME_HOSTS（カンマ区切り）のホスト（とそのサブドメイン）だけ許可する。
  3. javascript_tool は、リポジトリの studio_related_video.js（YouTube Studio の関連動画設定用）を実行する3つの形だけ許可する。
     (a) localStorage.setItem('rel_fn', `<そのファイルの関数本体と完全に一致>`)  (b) その関数の呼び出し  (c) localStorage.removeItem('rel_fn')
判断できない入力・設定不備は拒否側に倒す。拒否は終了コード2＋標準エラー出力。
"""
import json, os, sys, re
from urllib.parse import urlparse

def deny(msg):
    print("handoff-chrome-guard: " + msg, file=sys.stderr)
    sys.exit(2)

try:
    data = json.load(sys.stdin)
except Exception:
    deny("入力を読めないため拒否")

tool = str(data.get("tool_name", ""))
inp = data.get("tool_input") or {}
sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(data.get("session_id", "")))
dev = os.environ.get("HANDOFF_CHROME_DEVICE_ID", "").strip()
hosts = [h.strip().lower() for h in os.environ.get("HANDOFF_CHROME_HOSTS", "").split(",") if h.strip()]
state_dir = os.environ.get("HANDOFF_CHROME_STATE_DIR", "")
if not (dev and hosts and state_dir and sid):
    deny("設定不備（device_id・hosts・state_dir・session_id のどれかが無い）")

name = tool.split("__")[-1]
REL_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "studio_related_video.js")
CALL_RE = re.compile(r"""^await \(new Function\('KW','FORCE',localStorage\.getItem\('rel_fn'\)\)\)\("([^"\\\n`$]{1,80})", (true|false)\)$""")

def related_js_ok(text):
    text = text.strip()
    if text == "localStorage.removeItem('rel_fn')" or CALL_RE.match(text):
        return True
    head, tail = "localStorage.setItem('rel_fn', `", "`)"
    if text.startswith(head) and text.endswith(tail):
        try:
            src = open(REL_JS, encoding="utf-8").read()
        except Exception:
            return False
        marker = "// ↓ 関数本体"
        i = src.find(marker)
        if i < 0:
            return False
        body = src[src.index("\n", i) + 1:].strip()
        return text[len(head):-len(tail)].strip() == body
    return False
flag = os.path.join(state_dir, "selected-" + sid)

if len(sys.argv) > 1 and sys.argv[1] == "post":
    # PostToolUse: 成功した select_browser で印を立て、list_connected_browsers の結果で印を検証する
    if name == "select_browser" and str(inp.get("deviceId", "")) == dev:
        os.makedirs(state_dir, exist_ok=True)
        open(flag, "w").write(dev)
    elif name == "list_connected_browsers":
        resp = data.get("tool_response")
        text = ""
        if isinstance(resp, list):
            text = "".join(str(b.get("text", "")) for b in resp if isinstance(b, dict))
        elif isinstance(resp, dict):
            c = resp.get("content")
            text = "".join(str(b.get("text", "")) for b in c if isinstance(b, dict)) if isinstance(c, list) else json.dumps(resp)
        else:
            text = str(resp or "")
        try:
            browsers = json.loads(text)
            in_use = [b.get("deviceId") for b in browsers if b.get("inUse")]
            ours = any(b.get("deviceId") == dev for b in browsers)
            if (not ours or (in_use and any(d != dev for d in in_use))) and os.path.exists(flag):
                os.remove(flag)
        except Exception:
            pass
    sys.exit(0)

if name == "list_connected_browsers":
    sys.exit(0)
if name == "select_browser":
    if str(inp.get("deviceId", "")) != dev:
        deny("制作専用ブラウザ以外は選べない")
    sys.exit(0)
if not os.path.exists(flag):
    deny("先に select_browser で制作専用ブラウザ（device_id %s）を選び、成功させること（続けて list_connected_browsers で inUse が制作専用になったか確認する）" % dev)
if name == "navigate":
    url = str(inp.get("url", "")).strip()
    if url.lower() in ("back", "forward"):
        sys.exit(0)
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in hosts):
        deny("許可されていないサイト: %s（許可: %s）" % (host or url, ", ".join(hosts)))
if name == "javascript_tool":
    if not related_js_ok(str(inp.get("text", ""))):
        deny("javascript_tool は studio_related_video.js の実行（保存・呼び出し・片付け）だけ許可")
sys.exit(0)
