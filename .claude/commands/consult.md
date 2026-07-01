# /consult — Claude × Gemini 対話コンサルティング

ユーザーから課題を受け取り、Claude と Gemini が2ターン対話したうえで
Sonnet 5 が両者の意見を統合して最終提案を行うコマンド。

---

## フロー概要

```
ユーザー（課題）
  → Claude が課題を整理・フレーミング
  → Gemini Turn 1（課題投入）
  → Claude が T1 回答を読んでコメント生成
  → Gemini Turn 2（Claude コメント投入）
  → Sonnet 5 が全ダイアログ + 両者の立場を統合して最終提案
  → ユーザーへ提示
```

---

## STEP 1 — 課題を受け取り、Gemini 向け Turn 1 プロンプトを生成する

ユーザーの課題説明をもとに、以下の観点でGemini向けプロンプトを構成する：

- **背景**: 何を作っているか・どんな問題に取り組んでいるか
- **課題の核心**: 具体的に何を改善・解決したいか
- **制約・前提**: 変えられないもの、守るべきルール
- **求めるもの**: 批判的意見 / アイデア / 設計案 など

システムプロンプトは以下で固定:
```
You are an expert reviewer and technical consultant. Give candid, direct feedback.
Be specific. Challenge assumptions. Point out risks. Suggest concrete alternatives.
Respond in Japanese.
```

---

## STEP 2 — Gemini Turn 1

```bash
HISTORY=/tmp/sc_consult_history.json
rm -f "$HISTORY"   # 前回セッションをクリア

python3 $HOME/samurai-chronicles/sc_gemini_consult.py \
  --message "<Turn1プロンプト>" \
  --save-history "$HISTORY" \
  --system "You are an expert reviewer and technical consultant. Give candid, direct feedback. Be specific. Challenge assumptions. Point out risks. Suggest concrete alternatives. Respond in Japanese."
```

Gemini の T1 回答を画面に出力する：

```
━━━ Gemini Turn 1 ━━━
{T1回答の全文}
━━━━━━━━━━━━━━━━━━━━
```

---

## STEP 3 — Claude が T1 回答を読んでコメントを生成する

T1 回答を受けて Claude 自身が以下を行う（**画面には表示しない**）：

- T1 で正しいと思う点・採用したい点
- T1 に対する疑問・反論・追加視点
- T1 では触れられていない重要な観点

これらをまとめて Turn 2 用のコメントテキストを生成する。

---

## STEP 4 — Gemini Turn 2

```bash
python3 $HOME/samurai-chronicles/sc_gemini_consult.py \
  --message "<Claudeのコメント>" \
  --history-file "$HISTORY" \
  --save-history "$HISTORY"
```

Gemini の T2 最終回答を画面に出力する：

```
━━━ Gemini Turn 2（最終） ━━━
{T2回答の全文}
━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## STEP 5 — Sonnet 5 が統合して最終提案を生成する

以下の情報を Sonnet 5 subagent に渡す：

- ユーザーの元の課題
- Claude が Turn 1 に渡したプロンプト（Claudeの問題整理）
- Gemini T1 回答
- Claude の Turn 2 コメント（Claudeの立場・意見）
- Gemini T2 最終回答

Sonnet 5 への指示:
```
あなたは上記の Claude × Gemini 対話を踏まえて最終提案をまとめる統合役です。

以下を行ってください（日本語で）：
1. 【Claude・Gemini の合意点】両者が共通して指摘していること
2. 【意見の相違点】立場が異なった点と、どちらの見方が妥当か
3. 【最終提案】課題に対する具体的な推奨アクション（優先度つき）
4. 【懸念・リスク】採用前に確認すべき点

実装はしない。提案のみ。
```

Sonnet 5 の出力をそのままユーザーに提示する。

---

## 定数

- Geminiモデル: `gemini-2.5-flash`
- 統合モデル: `Sonnet 5`（Agent tool の `model="sonnet"`）
- 履歴ファイル: `/tmp/sc_consult_history.json`（セッション開始時にクリア）
