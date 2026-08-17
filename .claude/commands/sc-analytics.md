# /sc-analytics — Samurai Chronicles YouTube アナリティクス分析

蓄積されたYouTube Analyticsデータから相対的な強弱パターンを把握し、
制作ルール（タイトル型・登場人物数・トピック角度・人物選定等）に反映するコマンド。
月1回程度の低頻度想定（毎エピソードではない）。

---

## STEP 1 — データ最新化

```bash
python3 sc_yt_download_reports.py
```

**注意:** `analytics/raw/` は `.gitignore` 対象のため、他端末からの `git pull` 後は
ローカルのCSVが消えていることがある。分析前は必ず実行して最新化すること。

## STEP 2 — 基本集計

```bash
python3 sc_yt_analyze.py --full
```

CTR/維持率のトップ・ボトム、タイトル型別、登場人物数別が出力される
（`--top` `--min-impressions` `--min-views` でしきい値調整可）。

## STEP 3 — 追加分析（必要に応じて）

過去に有効だった軸（`sc_yt_analyze.py` の `build_stats()` を再利用し、
`topics_queue.json` の `person`/`era`/`angle` と episode_id で突き合わせる）:

- タイトル型別（**外れ値除外での再検証必須** — 少数の外れ値1本で結論が
  逆転することがある。2026-08-02分析で型A/DのCTR優位がep030除外で消えた事例あり）
- 登場人物数別
- angle別（overview/philosophy/key_event/death等）
- 人物知名度別（有名人物 vs マイナー人物）
- era別
- リタイトル等、過去に打った施策のBefore/After効果検証

## STEP 4 — 解釈・提言をOpusサブエージェントに委任（2026-08-04〜）

**理由:** STEP 1-3（集計の実行自体）はスクリプトでモデル非依存。Opusが効くのは
「その結果をどう解釈し、次のアクションにどうつなげるか」の部分のみ。統計的有意性の
判断（小さい n での早合点回避）や複数指標を横断した傾向解釈は深い判断力が要るタスクで、
かつ本コマンドは数週間に1回程度の低頻度なのでOpus利用によるコスト増もほぼ無視できる。

STEP 1-3で計算した**集計結果**（生CSVではなく集計済みの数値・比較表）を `Agent` ツールで
`model: "opus"` のサブエージェントに渡す。サブエージェントは会話履歴を持たないため、
以下を明示的に含めること：

- STEP 1-3で得た集計結果（数値・比較表）全文
- 過去の分析結果・意思決定の記録（project memory の YouTube アナリティクス関連メモの要約）
- 現在の `topics_queue.json` の pending 分（person/era/angle構成）のサマリ

Agentプロンプト:
```
以下はSamurai ChroniclesのYouTubeアナリティクス集計結果です。

{集計結果}

過去の分析結果・意思決定の記録:
{project memoryの要約}

現在のトピックキュー（pending分のperson/era/angle構成）:
{サマリ}

以下を行ってください（日本語で）：
1. 各指標について、サンプルサイズ・外れ値の影響を踏まえて統計的に妥当な解釈かを検証する
   （小さいnでの早合点、外れ値1本への依存等がないか）
2. 複数指標を横断した傾向を統合的に解釈する
3. 具体的なアクション提言（優先度つき）— タイトル型・登場人物数・トピック角度・
   人物選定・リタイトル等、制作ルールに反映すべき変更
4. まだ判断を保留すべき（データ不足の）項目があれば明記する
```

`run_in_background: false` で結果を待つ。

## STEP 5 — ユーザーへ提示・承認

Opusの提言をそのままユーザーに提示し、`.claude/commands/sc-new.md` 等への反映可否を確認する。
ここで自動確定はしない。

## STEP 6 — 承認内容の反映

承認が得られた項目について:
- `.claude/commands/sc-new.md` の該当ルールを更新
- 必要なら `topics_queue.json` の pending トピックの `notes` を更新
- 分析結果と意思決定の経緯を project memory に記録（数値・根拠・Why・How to applyを含める）
