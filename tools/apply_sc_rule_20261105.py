#!/usr/bin/env python3
"""SC 確認ルール恒常化（2026-11-05）の適用スクリプト。ユーザーが Terminal で実行する。

(a) repos.json の samurai-chronicles 設定を更新
    - .claude/ 配下の編集を無人実行で許可（許可ディレクトリ一覧に追加）
    - 確認ポイント(1)を「確認ページは sc-manager の判断で通過し、止まらない」に更新
      （(2)(3)(4) は現行どおり）
(b) .claude/commands/sc-new.md に前回の修正提案を反映し、自動メモリの旧注記を置き換え、
    sc-new.md だけ git add・commit・push する。

安全策:
  - 書き込み前に全対象のバックアップ（<元ファイル>.bak-<日時>）を取る
  - 置換対象が見つからない項目が1つでもあれば、何も変更せず中断して報告する
  - 適用済みの項目は自動でスキップ（冪等）
  - --dry-run で変更なしの事前検査だけができる

使い方:
  python3 tools/apply_sc_rule_20261105.py --dry-run
  python3 tools/apply_sc_rule_20261105.py
  （repos.json が自動で見つからない場合は --repos-json /path/to/repos.json を付ける）
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC_NEW = os.path.join(REPO, ".claude", "commands", "sc-new.md")
MEM_DIR = os.path.expanduser("~/.claude/projects/-Users-claude-samurai-chronicles/memory")
MEM_FEEDBACK = os.path.join(MEM_DIR, "feedback_thumbnail_bgm_auto_confirm.md")
MEM_INDEX = os.path.join(MEM_DIR, "MEMORY.md")
ALLOW_DIRS_NEW = [
    os.path.join(REPO, ".claude", "commands"),
    os.path.join(REPO, ".claude", "agents"),
]
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

MGR = "sc-manager"
RULE_PARAGRAPH = """**2026-11-05〜 確認ルール（ユーザー決定・恒常）:**
1. サムネイル・BGM・シーン画像の統合確認で、ユーザー確認は行わない。確認ページ生成後に sc-manager を呼び、成果物そのもので進行可否を判断させる。
2. 細部（再生成の要否・差し替え・軽微な修正）は管理担当・担当者が決める。
3. ユーザーが確認するのは完成動画（STEP 6。本編・学習版）のみ。
4. アップロードはセッション（人が見ている対話）で実施する。無人実行ではアップロード・公開・コメント返信・関連動画の設定を行わない。

"""
INTEGRATED_NOTE = """
**【2026-11-05〜】この統合確認のユーザー確認は省略する。** 確認ページ（`sc_scene_review.py`）生成後に
sc-manager を呼び、サムネイル・BGM・シーン画像・確認ページの成果物そのもので進行可否を判断させる。
進行可なら STEP 4 へ進む。（Opusでも直らない画像・要相談の扱いは、ユーザー判断待ちのため従来どおり。）ユーザー確認は完成動画
（STEP 6。本編・学習版）のみ。以下の「提示するメッセージ」は、sc-manager への依頼・
事後報告の内容として読み替える。
"""

# (a) 確認ポイント(1)の新文言
CP1_NEW = ("(1)本編の確認ページ（~/Desktop/SC/ep{NNN}_review.html）: 止まらない。"
           "`python3 sc_scene_review.py --episode ep{NNN}` で確認ページを作ったら、sc-manager（管理担当）を呼び、"
           "サムネイル・BGM・シーン画像・確認ページの成果物そのものを確認させて進行可否を判断させ、"
           "進行可なら STEP 4 以降へ進む（ユーザー確認は不要。確認ページの生成だけで確認したことにはならない）。")
CP1_RE = re.compile(r"\(1\)本編の確認ページを確認する時点[^\n]*?出てから）。")
PASS_OLD = "その確認ポイントの『確認OK』が明記されている場合に限り"
PASS_NEW = PASS_OLD + "（確認ポイント(1)は sc-manager の判断で通過するため、この条件は不要）"
STOP_OLD_RE = re.compile(r"次の\(1\)〜\(3\)の時点で必ず止まり")
STOP_NEW = "次の(2)(3)の時点で必ず止まり"

# (b) sc-new.md の置換（old, new）。new が既に含まれていれば適用済みとしてスキップ
EDITS = [
    ("| *(確認待ち)* | サムネイル・BGM・シーン画像を1回のメッセージでまとめて確認 | 要確認 |",
     "| *(管理担当の確認)* | サムネイル・BGM・シーン画像を sc-manager が確認して進行可否を判断（ユーザー確認なし） | 約3〜5分 |"),
    ("Google Driveへ移動・BGM本登録（統合確認のOK後に実行）",
     "Google Driveへ移動・BGM本登録（統合確認で sc-manager が進行可と判断した後に実行）"),
    ("**合計目安: 約100〜130分**（確認待ち・再生成除く）",
     RULE_PARAGRAPH + "**合計目安: 約100〜130分**（確認待ち・再生成除く）"),
    ("サムネイル・BGMは**ユーザーに提示し、明示的なOKを得てから次に進む**という方針自体は\n"
     "2026-07-28から変わらないが、**確認を求めるタイミングは",
     "サムネイル・BGMは**ユーザーではなく sc-manager が確認して進行可否を判断する**"
     "（2026-11-05〜。それ以前はユーザーの明示的なOKが必要だった）。**確認のタイミングは"),
    ("**ユーザーへの提示・試聴確認は\n  STEP5C後の統合確認まで行わない**",
     "**ユーザーへの提示・試聴確認は行わない\n  （STEP5C後の統合確認で sc-manager が判断する。2026-11-05〜）**"),
    ("### 統合確認 — サムネイル・BGM・シーン画像をまとめて確認（2026-08-04〜）\n",
     "### 統合確認 — サムネイル・BGM・シーン画像をまとめて確認（2026-08-04〜）\n" + INTEGRATED_NOTE),
    ("\nOKが出るまで STEP 4 には進まない。",
     "\nsc-manager の進行可の判断が出るまで STEP 4 には進まない。"),
    ("後の統合確認でユーザーのOKが出てから実行する",
     "後の統合確認（sc-manager の進行可の判断）が出てから実行する"),
]

MEM_MARK = "【2026-11-05 更新】"
MEM_NOTE = (MEM_MARK + "この方針は置き換えられた。統合確認のユーザー確認は省略し、sc-manager が成果物そのもので"
            "進行可否を判断する。ユーザー確認は完成動画（STEP 6。本編・学習版）のみ。アップロードはセッションで実施。"
            "以下は2026-07-28時点の旧方針（履歴）。\n\n")
MEM_INDEX_OLD = ("- [サムネイル・BGM・画像のユーザー確認必須化](feedback_thumbnail_bgm_auto_confirm.md) — "
                 "2026-07-28〜自動確定を廃止。試聴・目視でOKを得るまでDrive移動/動画生成に進まない")
MEM_INDEX_NEW = ("- [サムネイル・BGM・画像の確認ルール](feedback_thumbnail_bgm_auto_confirm.md) — "
                 "2026-11-05〜統合確認のユーザー確認は省略しsc-managerが進行可否を判断。ユーザー確認は完成動画のみ（旧: 2026-07-28〜必須化）")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def find_repos_json(arg):
    if arg:
        return os.path.abspath(os.path.expanduser(arg))
    home = os.path.expanduser("~")
    pats = ["~/repos.json", "~/*/repos.json", "~/*/*/repos.json", "~/.config/*/repos.json",
            "~/Library/Application Support/*/repos.json"]
    hits = []
    for pat in pats:
        for p in glob.glob(os.path.expanduser(pat)):
            try:
                if "samurai-chronicles" in read(p):
                    hits.append(p)
            except OSError:
                pass
    hits = sorted(set(hits))
    if len(hits) == 1:
        return hits[0]
    sys.exit("repos.json を一意に特定できません（候補: %s）。--repos-json で指定してください。" % hits)


def find_entry(data):
    """samurai-chronicles を指す dict（repo 設定）を探す。"""
    found = []

    def walk(o):
        if isinstance(o, dict):
            if any(isinstance(v, str) and v.rstrip("/").endswith("samurai-chronicles") for v in o.values()) \
               or any(k == "samurai-chronicles" for k in o):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    # キーが samurai-chronicles の場合は、その値の dict を返す
    if isinstance(data, dict) and isinstance(data.get("samurai-chronicles"), dict):
        return data["samurai-chronicles"]
    cands = []
    for o in found:
        c = o["samurai-chronicles"] if isinstance(o.get("samurai-chronicles"), dict) else o
        if not any(c is x for x in cands):
            cands.append(c)
    if len(cands) != 1:
        sys.exit("repos.json 内の samurai-chronicles の設定候補が %d 個あり、1つに特定できないため中断します（変更なし）。" % len(cands))
    return cands[0]


def plan_repos_json(path):
    """変更後の JSON オブジェクトと、変更内容のメモ（list）を返す。見つからなければ error 文字列を返す。"""
    raw = read(path)
    data = json.loads(raw)
    entry = find_entry(data)
    if entry is None:
        return None, None, ["repos.json に samurai-chronicles の設定が見つからない"], raw
    notes, errors = [], []

    # (a-1) 許可ディレクトリ一覧（/Desktop/SC や /tmp/sc を含む文字列リスト）に .claude を追加
    lists = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            if o and all(isinstance(x, str) for x in o) and any(("/Desktop/SC" in x or "/tmp/sc" in x) for x in o):
                lists.append(o)
            else:
                for v in o:
                    walk(v)
    walk(entry)
    if len(lists) != 1:
        errors.append("許可ディレクトリの一覧（/Desktop/SC や /tmp/sc を含む文字列リスト）が %d 個あり、1つに特定できない。"
                      "repos.json の構造を確認し、.claude の許可を手で追加してください" % len(lists))
    else:
        lst = lists[0]
        if any(not x.startswith("/") for x in lst):
            errors.append("許可ディレクトリ一覧の項目が素のパスでない（例: Edit(...) 形式）。書式を合わせられないため手で追加してください")
        else:
            added = [d for d in ALLOW_DIRS_NEW if d not in lst]
            if added:
                lst.extend(added)
                notes.append("許可ディレクトリに追加: %s" % ", ".join(added))
            else:
                notes.append("許可ディレクトリ: 追加済み（スキップ）")

    # (a-2) 確認ポイント(1)の文言・止まる時点・通過条件
    cnt = {"cp1": 0, "cp1_done": 0, "stop": 0, "stop_done": 0, "pass": 0, "pass_done": 0, "bad": 0}

    def sub_strings(o):
        if isinstance(o, dict):
            return {k: sub_strings(v) for k, v in o.items()}
        if isinstance(o, list):
            return [sub_strings(v) for v in o]
        if isinstance(o, str):
            if CP1_NEW in o:
                cnt["cp1_done"] += 1
            ms = CP1_RE.findall(o)
            if ms:
                if len(ms) != 1 or any(("(2)" in m or "(3)" in m or "(4)" in m) for m in ms):
                    cnt["bad"] += 1
                else:
                    cnt["cp1"] += 1
                    o = CP1_RE.sub(lambda m: CP1_NEW, o)
            if STOP_NEW in o:
                cnt["stop_done"] += 1
            elif STOP_OLD_RE.search(o):
                cnt["stop"] += 1
                o = STOP_OLD_RE.sub(STOP_NEW, o)
            if PASS_NEW in o:
                cnt["pass_done"] += 1
            elif PASS_OLD in o:
                cnt["pass"] += 1
                o = o.replace(PASS_OLD, PASS_NEW)
            return o
        return o
    new_entry = sub_strings(entry)
    for key, label in (("cp1", "確認ポイント(1)の文言"), ("stop", "『次の(1)〜(3/4)の時点で必ず止まり』"),
                       ("pass", "通過条件『確認OKが明記』")):
        if cnt[key] == 1:
            notes.append("%s を更新" % label)
        elif cnt[key] > 1:
            errors.append("%s が複数か所にあり一意でない" % label)
        elif cnt[key + "_done"]:
            notes.append("%s: 更新済み（スキップ）" % label)
        else:
            errors.append("%s が見つからない" % label)
    if cnt["bad"]:
        errors.append("確認ポイント(1)の一致範囲が(2)〜(4)にかかる、または複数一致のため、安全に置換できない")
    if errors:
        return None, None, errors, raw

    # new_entry を data に差し戻す
    def replace(o):
        if o is entry:
            return new_entry
        if isinstance(o, dict):
            return {k: replace(v) for k, v in o.items()}
        if isinstance(o, list):
            return [replace(v) for v in o]
        return o
    return replace(data), notes, [], raw


def dump_like(raw, obj):
    indent = 2
    m = re.search(r"\n( +)\"", raw)
    if m:
        indent = len(m.group(1))
    elif "\n" not in raw.strip():
        indent = None
    s = json.dumps(obj, ensure_ascii=False, indent=indent)
    return s + ("\n" if raw.endswith("\n") else "")


def plan_text_edits(text):
    """(new_text, applied, skipped, missing)"""
    applied, skipped, missing = [], [], []
    for i, (old, new) in enumerate(EDITS, 1):
        if new in text:
            skipped.append(i)
        elif old in text:
            if text.count(old) != 1:
                missing.append("%d（置換対象が複数あり一意でない）" % i)
            else:
                text = text.replace(old, new)
                applied.append(i)
        else:
            missing.append("%d（置換対象が見つからない: %r…）" % (i, old[:40]))
    return text, applied, skipped, missing


def plan_memory():
    out = []  # (path, newtext) / 問題は missing
    missing = []
    t = read(MEM_FEEDBACK) if os.path.exists(MEM_FEEDBACK) else None
    if t is None:
        missing.append("メモリファイルが無い: " + MEM_FEEDBACK)
    elif MEM_MARK in t:
        pass
    else:
        m = re.match(r"(---\n.*?\n---\n\n?)", t, re.S)
        if not m:
            missing.append("メモリファイルの frontmatter を認識できない")
        else:
            out.append((MEM_FEEDBACK, m.group(1) + MEM_NOTE + t[m.end():]))
    ix = read(MEM_INDEX) if os.path.exists(MEM_INDEX) else None
    if ix is None:
        missing.append("MEMORY.md が無い")
    elif MEM_INDEX_NEW in ix:
        pass
    elif MEM_INDEX_OLD in ix:
        out.append((MEM_INDEX, ix.replace(MEM_INDEX_OLD, MEM_INDEX_NEW)))
    else:
        missing.append("MEMORY.md に旧索引行が見つからない")
    return out, missing


def git(*args):
    return subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rj = find_repos_json(a.repos_json)
    print("repos.json:", rj)
    new_obj, a_notes, a_err, rj_raw = plan_repos_json(rj)
    sc_text = read(SC_NEW)
    new_sc, applied, skipped, b_missing = plan_text_edits(sc_text)
    mem_out, mem_missing = plan_memory()

    problems = a_err + ["sc-new.md 項目 " + x for x in b_missing] + mem_missing
    if problems:
        print("\n【中断】次の項目が見つからないため、何も変更していません:")
        for p in problems:
            print(" -", p)
        sys.exit(2)

    print("\n(a) repos.json:")
    for n in a_notes:
        print(" -", n)
    print("(b) sc-new.md: 適用 %s / 適用済みスキップ %s（全%d項目）" % (applied, skipped, len(EDITS)))
    print("    メモリ: %s" % ([os.path.basename(p) for p, _ in mem_out] or "適用済み（スキップ）"))
    if a.dry_run:
        print("\n--dry-run のため変更しません。")
        return

    # バックアップ → 書き込み
    targets = [rj, SC_NEW] + [p for p, _ in mem_out]
    for p in targets:
        write(p + ".bak-" + STAMP, read(p))
        print("バックアップ:", p + ".bak-" + STAMP)
    new_rj_text = dump_like(rj_raw, new_obj)
    if new_rj_text != rj_raw:
        write(rj, new_rj_text)
    if new_sc != sc_text:
        write(SC_NEW, new_sc)
    for p, t in mem_out:
        write(p, t)

    # git（sc-new.md のみ。バックアップは add しない）
    if new_sc != sc_text:
        rel = os.path.relpath(SC_NEW, REPO)
        for cmd in (["add", rel],
                    ["commit", "-m",
                     "SC確認ルール恒常化: sc-new.md に統合確認のユーザー確認省略（sc-manager判断）を反映\n\n"
                     "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>", "--", rel]):
            r = git(*cmd)
            if r.returncode:
                print("git %s 失敗:\n%s%s" % (cmd[0], r.stdout, r.stderr))
                sys.exit(3)
        r = git("push")
        if r.returncode:
            git("pull", "--rebase", "--autostash")
            r = git("push")
        print("git push:", "成功" if r.returncode == 0 else "失敗\n" + r.stderr)
        if r.returncode:
            sys.exit(4)
    print("\n完了。バックアップ（*.bak-%s）は確認後に手で削除してください。" % STAMP)


if __name__ == "__main__":
    main()
