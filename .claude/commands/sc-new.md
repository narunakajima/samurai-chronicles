# /sc-new — Samurai Chronicles 新エピソード生成

topics_queue.json から次のトピックを選び、動画生成まで一気に進めるコマンド。

---

## 起動時プレビュー（毎回必ず表示する）

コマンド起動直後、STEP 1 に入る前に以下を**そのまま**表示する：

```
## `/sc-new` — 作業プレビュー

| ステップ | 内容 | 所要時間 |
|---|---|---|
| STEP 1  | 次のトピック確認（人物重複チェック・S19予告確認） | 約5分 |
| STEP 2A | エピソードJSON生成（20シーン） | 約5〜10分 |
| STEP 2B | JSONファイル保存 + キュー更新 | 即時 |
| STEP 3A/3B/3C | 制作確認書・サムネイル・BGM選定（並行） | 約30〜40分 |
| *(確認待ち)* | サムネイル・BGMは必ずユーザー確認（試聴・目視）。ナレーションは⚠️がある場合のみ | 要確認 |
| STEP 4  | Google Driveへ移動 | 約1分 |
| STEP 5A/5B | TTS生成 + 画像生成 16:9（並行） | 約10分 |
| STEP 5A/5B | TTS（teaser・shorts）+ 画像生成 9:16（並行） | 約3分 |
| STEP 5C | 画像QA（＋再生成時 +3〜5分）+ シーン画像のユーザー確認 | 要確認 |
| STEP 5D | zoom_anchor 判定 | 約3〜5分 |
| STEP 6  | 動画生成（本編+Shorts） | 約40〜50分 |
| STEP 6  | 字幕生成 | 約1分 |

**合計目安: 約100〜130分**（確認待ち・再生成除く）
```

表示後、ユーザーの確認を待たずにそのまま STEP 1 へ進む。

### 各ステップの進捗報告（必須）

各ステップ完了時に必ず以下の形式で報告してから次のステップへ進む：

```
✅ STEP 1 完了 — ep{NNN} 確定（{person}）
✅ STEP 2A 完了 — JSON生成（{total_scenes}シーン）
✅ STEP 2B 完了 — ファイル保存・キュー更新

STEP 3 開始（並行処理）
  ├─ 3A: 制作確認書生成
  ├─ 3B: サムネイル生成
  └─ 3C: BGM選定
```

STEP 3A/3B/3C はすべて完了してから一括で完了報告する（個別には報告しない）。

---

## 定数

- エピソードJSON: `$HOME/samurai-chronicles/episodes/`
- トピックキュー: `$HOME/samurai-chronicles/topics_queue.json`
- Google Drive: `~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/`

---

## STEP 1 — 次のトピックを確認する

`topics_queue.json` を読み込み、`status: "pending"` の件数を確認する。

### 残り5件以下の場合 — トピック補充

新しいトピックを5件提案し、ユーザーに確認してもらう。

**再登場ルール（必須）：**
- すでに登場済みの人物を提案する場合は、`notes` に**前回との違い（新角度）を必ず明記**する
  - 例：`"notes": "ep002で本能寺を扱ったが、今回は比叡山焼き討ちに特化。残虐性vs合理性の議論"` 
- 「別の有名なエピソードがある」だけでは理由として不十分。視聴者が**前回と全く違う何かを得られるか**で判断する
- 新角度が明確でない場合は、未登場の人物を優先する

**角度（angle）選定の優先度（実績データに基づく・2026-08-02分析、n=47本）：**
- `angle: "overview"`（生涯・人物像の全体像）と `"philosophy"`（思想・価値観）はCTR・維持率とも
  最上位（overview: CTR3.54%/維持率20.4%、philosophy: CTR3.61%/維持率22.6%）。**新規提案では
  この2つを優先する。**
- `"key_event"`（単一事件の顛末）はCTR2.71%/維持率17.6%、`"death"`（死の謎）はCTR2.12%/維持率9.2%と
  両軸で最弱。この2つは提案数を絞り、扱う場合も「事件そのもの」ではなく「その事件が物語る
  人物の生き方」に重心を置く前提で `notes` に明記する。
- `"character"`（人物の一面切り取り）はCTRは悪くないが維持率が弱い（14.2%）。クリックされても
  離脱されやすいため多用しない。

**人物選定の優先度（実績データに基づく・2026-08-02分析）：**
- 知名度の低い人物（マイナー武将・参謀・脇役）の方が、有名人物（信長・家康・秀吉・武蔵・信玄・
  謙信・西郷等）より平均CTRが高い（マイナー3.55% vs 有名2.54%）。維持率はほぼ差がないため、
  **CTR目的では知られざる人物を優先する。**
- 特に「知られざる軍師・参謀」タイプ（例：黒田官兵衛はCTR9.85%/6.07%の2本がトップ2）が強い
  傾向がある。同系統（主君を支える策士・二番手のブレーン）の人物は積極的に候補に入れる。

提案フォーマット：
```
残りトピックが少なくなりました。新しい候補を5件提案します：

1. ep031「...」（era / Priority A）
   ※ メモ（再登場の場合：前回ep00Xとの違い）
2. ep032「...」
...

追加しますか？（はい / 修正あり / 不要）
```

OKが取れたら `topics_queue.json` の `queue` に追記し、`total_topics` と `last_updated` を更新する。

---

`status: "pending"` のうち**配列の先頭（最初に現れるもの）**を候補とする。（episode_id の番号順ではなく、配列の並び順で決まる）

### 人物重複チェック（必須）

候補を提案する前に、直近5件の `status: "published" | "in_production"` のエピソードと `person` フィールドを照合する。

- 直近5件に**同じ `person`** が含まれている場合 → その候補をスキップし、`person` が重ならない最初の `pending` を選ぶ
- 同じ人物しか残っていない場合 → 候補を提案しつつ「直近に同じ人物が続いています」と警告する

表示フォーマット：
```
次のエピソード候補：

ep002「The Honnoji Incident」（Sengoku / Priority A）
※ ep001 アウトロでティーザー済み

これにしますか？（はい / 別のトピックを指定）
```

---

## STEP 2A — エピソード内容を生成する

選ばれたトピックをもとに、以下を含む完全なエピソードJSONを生成する。

**JSONの内容は画面に出力しない。** 生成後すぐにファイルへ保存する。

### 生成方法（2026-07-28〜: Opusサブエージェントに委任）

このSTEPの生成（エピソードJSON全体の作成）は `Agent` ツールで `model: "opus"` を指定した
サブエージェントに任せる。理由: 龍馬の髪型・ブーツの着用時期・実在人物の甲冑有無といった
細かい史実知識の精度がOpusの方が高く、image_promptの時代考証ミスを減らせるため
（2026-07-28、ep068制作中にSonnetの史実知識不足に起因する複数の誤りが発覚したことを受けての変更）。

サブエージェントは会話履歴を持たないため、Agentプロンプトには以下を明示的に含めること：
- 選ばれたトピック情報（`episode_id`, `title`, `era`, `priority`, `person`, `angle`, `notes`）
- このSTEP 2A以下（本ファイルの「生成ルール」節全文 — タイトル型・ナレーション・Hookルール・
  画像プロンプト・Ken Burns・character_ref・登場人物数上限・shorts関連フィールド・
  JSONフォーマット・youtube_description必須フォーマット）をそのまま転記する
- STEP 1で確認済みのS19次回予告の対象エピソード情報
- 出力先パス `$HOME/samurai-chronicles/episodes/ep{NNN}.json` に直接JSONファイルを
  書き込むよう指示する（オーケストレーター側では保存しない）
- 新キャラクターが必要な場合は `characters/{name}.txt` も作成するよう指示する

Agent呼び出しは `run_in_background: false`（結果を待ってから STEP 2B に進む必要があるため）。
Agentの最終報告はユーザーには表示しない（画面に出力しないという方針は変わらない）。
オーケストレーター（この会話のモデル）は完了後、保存されたJSONのシーン数・フォーマットの
妥当性のみを検証し、STEP 2Bへ進む。

### 生成ルール

**YouTube タイトルの型（CTR最大化）:**

海外歴史チャンネルで再生数が取れるタイトルには共通の型がある。必ずいずれかの型に当てはめること。

- 型A: `"The [Adjective] [Person] Who [Did Something Shocking]"`
- 型B: `"Why [Famous Person] Really [Did Something]"`
- 型C: `"The Real Reason [Famous Event] Happened"`
- 型D: `"The [Event] That Changed Japan Forever"`

**実績データに基づく優先度（2026-08-02 分析、外れ値補正済み・n=47本集計、更新）:** 型A/D「The X Who/That〜」は
型B「Why〜」より**維持率が優位**（20.6% vs 17.2%、外れ値ep030除外後）。この維持率優位は
2026-07分析からも再現している頑健なシグナル。
**CTRについては型A/Dの優位は消滅した**（データが増えた結果、外れ値ep030除外後で
型A/D 2.80% < 型B 3.09%と逆転）。したがって**型A/Dを選ぶ理由はCTRではなく維持率目的のみ**。
CTRを重視したい場合に型A/Dを無理に優先する根拠はない。型Bは「なぜ」の答えが動画内に
明確にある場合に使う。
なお型の効果は下記「登場人物数の上限」と交絡しており、**より根本的なのは
「主人公1人・1つの選択」への絞り込み**である。型選びよりこちらを優先すること。

× 避ける: `"The History of Miyamoto Musashi"`（説明的すぎる）
○ 良い: 裏切り・転落・奇跡・復讐など「人間ドラマ」としてフックを作る

シリーズ構成の場合はタイトル末尾に統一表記する:
```
例: "The Betrayal at Honnoji | Sengoku's Most Brutal Betrayals #1"
```

---

**ナレーション（各シーン）:**
- BBC/Netflix歴史ドキュメンタリー調の英語
- 1シーン約80〜100語（TTS読み上げ速度 約90語/分 → **実尺 約55〜70秒**）
- 各シーンで次シーンへの引きを作る
- hook → setup → rising_action → climax → falling_action → insight → teaser → outro の構成

**Hook シーン（scene_id: 1, type: "hook"）の特別ルール:**
- 必ず3文以内、合計40語以内
- 1文目: 衝撃の結論 or 問いかけ（10語以内、数字を含めると効果的）
- 2文目: 矛盾・謎・意外性（好奇心を刺激する）
- 3文目: 「続きを見れば分かる」という約束（疑問文推奨）
- "Today"、"In this video"、"Let me tell you" で始めない
- 例: "He fought 61 duels. He never lost once. But his greatest weapon wasn't his sword."

**画像プロンプト（image_prompt）:**
- 英語、具体的なシーン描写
- "Modern cinematic concept art style, dramatic lighting, film production illustration quality" のトーンを前提（BASE_CONTEXTが自動付与されるため重複不要）
- キャラクターが登場する場合は構図・位置・表情を具体的に記述

**Ken Burnsエフェクト（ken_burns）:**
- zoom_in / zoom_out / pan_right / pan_left / static から選択
- シーンの感情に合わせる（緊張感→zoom_in、引き→pan_right など）

**character_ref:**
- 主要キャラクターが登場するシーンのみ設定
- `characters/` フォルダにある名前を使用（例: "musashi", "kojiro"）
- 新キャラクターが必要な場合はメモしておく

**登場人物数の上限（必須・実績データに基づく制約 — タイトル型より上位の原則）:**
- エピソード全体を通して `character_ref` に設定する**人物は最大2人まで**にする
- 実績データ（2026-08-02分析、n=47本、07-13分析からも再現済み）: 1人構成は平均CTR 3.58%、
  2人構成は3.10%、3人以上は2.71%と、登場人物が増えるほどCTRが単調に低下している
  （タイトル・サムネで「誰の話か」が伝わりにくくなるため）
- タイトル型A/Dの優位もこの人数効果と交絡している。**「主人公1人・1つの選択」への
  絞り込みが最も頑健なシグナル**であり、タイトル型選びより優先する
- 対抗者・裏切り者など2人目までは許容するが、3人目以降は
  `character_ref: null` のまま「シルエット」「a rival general」等の匿名描写にとどめる
- 主人公が明確な1人構成が理想（型A/D「The X Who〜」との相性も良い）

**shorts_highlight_scene:**
- クライマックス**直前**のシーンを選ぶ（緊張が最高潮に達した瞬間）
- 「この後どうなる？」と思わせる引きを作り、本編への誘導フックにする
- climax シーンそのものではなく、その1〜2シーン前が理想

**shorts_hook_lines（必須・3行固定）:**
- Shorts冒頭クリップの画面上に表示されるテキストオーバーレイ（DIN Condensed Bold 白文字）
- **必ず3行で生成する**（空配列・省略禁止）
- 各行の文字数上限（フォントサイズ対応）:
  - 行1: **最大14文字**（fontsize=160 / 最大インパクト）→ 数字・短い断言
  - 行2: **最大18文字**（fontsize=125）→ 矛盾・謎の核心
  - 行3: **最大26文字**（fontsize=68）→ 問いかけまたは余韻
- すべて**大文字**で書く
- 良い例（ep046）: `["NEVER LOST.", "DIED ALONE.", "WAS HE MURDERED?"]`
- 良い例（ep044）: `["13 DAYS.", "ONE PERFECT COUP.", "WHY DID IT COLLAPSE?"]`
- 良い例（ep045）: `["61 DUELS.", "ZERO DEFEATS.", "WHY DID HE QUIT?"]`
- ❌ 避ける: 人物名のみ、説明的な文、14文字超の行1

**shorts_face_image_prompt:**
- Shorts冒頭クリップ（0秒目）専用の顔アップ画像プロンプト
- **必ず人物の顔が画面中央〜上部を占める構図**にする（スワイプ離脱防止）
- 含めるべき要素: キャラクター名・顔の表情・ドラマチックな照明・直視または強い視線
- 例: `"Extreme close-up of Uesugi Kenshin's face in the darkness of his castle. His eyes are open but lifeless, a general who never lost a battle — now fallen. Dramatic single torch light from below, deep shadows. Vertical portrait composition."`
- character_ref が null のエピソードでも、エピソードの主人公の顔を必ず描写する

**teaser_narration（本編トレイラーイントロ・冒頭30秒）:**
- 本編の最初に流れる「映画の予告編」スタイルのナレーション
- 合計30〜45語（約10〜15秒の読み上げ尺）
- 必ずクライマックスの瞬間から始める（視聴者を結末の直前に放り込む）
- 構成: 時・場所・状況（衝撃の一文）→ 矛盾・謎 → 「なぜそうなったのか？」への橋渡し
- 最後は必ず疑問形または「But who was this man?」「The answer lies here.」型で本編へ誘導
- 例（ep001）: "He stood alone on a windswept cliff — 61 duels behind him, not a single defeat. But in this moment, facing death, he carried no sword. Just a piece of wood. What kind of man walks into his final battle unarmed — and wins?"

**shorts_narration（Shorts専用トレイラーナレーション）:**
- 映画トレイラーのナレーター調。速く、力強く、間を削る
- 合計25〜35語以内（約10〜13秒の読み上げ尺）
- 構成: 数字/衝撃の事実 → 矛盾/謎 → クライマックスの断片 → 余韻を残す一言
- 必ず数字か固有名詞で始める（"61 duels." "One night." "Three hours." など）
- 本編全体の「予告編」として、最後に人物名または問いかけで締める
- 例（ep001）: "61 duels. Zero defeats. In Japan's most legendary battle, he didn't even bring a sword. He arrived three hours late — holding a wooden oar. And he still won. This is Miyamoto Musashi."

### JSONフォーマット

```json
{
  "episode_id": "ep{NNN}",
  "episode_title": "...",
  "youtube_title": "...",
  "youtube_description": "...",
  "youtube_tags": [...],
  "series_name": null,
  "series_number": null,
  "total_scenes": 20,
  "shorts_highlight_scene": N,
  "teaser_narration": "...",
  "shorts_narration": "...",
  "shorts_hook_lines": ["...", "...", "..."],
  "shorts_face_image_prompt": "...",
  "thumbnail_prompt": "...",
  "scenes": [
    {
      "scene_id": 1,
      "type": "hook",
      "duration_seconds": 10,
      "narration": "...",
      "image_prompt": "...",
      "ken_burns": "zoom_in",
      "character_ref": null
    },
    ...
  ]
}
```

### youtube_description の必須フォーマット

```
{フック文（2〜3文）}

🎌 Subscribe for new episodes every day:
https://www.youtube.com/@Samurai-Chronicles-JP

🌐 Official site: https://samurai-chronicles.com

🇯🇵 A Japanese perspective on Japanese history — created by a Japanese history enthusiast.

📚 References:
1. {参考文献1}
2. {参考文献2}
3. {参考文献3}

#{tag1} #{tag2} ...
```

シリーズ構成の場合は References の前に以下を追加する:
```
📺 Series: {series_name}
  #{series_number - 1} → {前エピソードタイトル（あれば）}
  #{series_number + 1} → Coming soon
```

**禁止:** 「AI」「AI-generated」などAI関連の文言は一切含めない。

---

## STEP 2B — JSONを保存し、topics_queue.json を更新する

```bash
# episodes/ に保存
$HOME/samurai-chronicles/episodes/ep{NNN}.json
```

該当エピソードの `status` を `"pending"` → `"in_production"` に変更して保存。

新キャラクターが登場する場合は `characters/{name}.txt` を作成する。

フォーマット（例）:
```
Oda Nobunaga: tall, imposing male warlord in his late 40s.
Sharp angular face, intense calculating eyes. Black lacquered armor.
Commanding presence. Carries a European arquebus as well as a katana.
```

---

## STEP 3 — 制作確認書・サムネイル・BGMを並行して準備する

制作確認書の生成（3A）・サムネイル画像生成（3B）・BGMダウンロード（3C）を**同時に**バックグラウンドで実行する。

### STEP 3A — 制作確認書（2026-07-28〜: Opusサブエージェントに委任）

**制作確認書の内容は画面に一切出力しない。**

このSTEPのファクトチェック・翻訳・確認書生成も `Agent` ツールで `model: "opus"` の
サブエージェントに任せる（STEP 2Aと同じ理由: 史実知識の精度）。Agentプロンプトには
`episodes/ep{NNN}.json` のパスと、以下の手順・フォーマット全文を含める。
`run_in_background: false` で結果を待つ。ファクトチェックで❌が見つかった場合の
`episodes/ep{NNN}.json` 直接修正も含めてサブエージェントに行わせてよい
（オーケストレーターは完了報告のみ受け取り、必要ならファイルの整合性を軽く確認する）。

#### 手順

1. エピソードJSONの全シーンを日本語に翻訳する
2. 全ナレーションのファクトチェック・英語QA・画像プロンプトQAを行う
3. **❌（Critical）が見つかった場合は、ユーザー確認なしに即座に自動修正する**
   - `episodes/ep{NNN}.json` の該当シーンを直接編集して修正
   - 修正後のナレーションで制作確認書を組み立てる
   - 保存される制作確認書には ❌ が残っていてはならない
4. 以下のフォーマットで `ep{NNN}_制作確認書.txt` を組み立てて `~/Desktop/SC/` に保存する

**制作確認書フォーマット:**
```
================================================================
  Samurai Chronicles EP{NNN} 制作確認書
  生成日: {YYYY-MM-DD}
================================================================

【エピソード概要】
----------------------------------------
エピソードID  : ep{NNN}
タイトル      : {episode_title}
YouTube タイトル: {youtube_title}
総シーン数    : {total_scenes}
Shorts シーン : S{shorts_highlight_scene:02d}
BGM           : ❌ 未選択

================================================================
【年号・日付チェック】
================================================================

ナレーション全シーンに登場する年号・日付・期間をすべて抜き出し、
1件ずつ正確性を検証する。「おそらく正しい」は ❌ として扱う。

| シーン | 記載内容 | 正誤 | 正しい情報 |
|--------|----------|------|------------|
| S{N}   | ...      | ✅/❌ | ...       |

年号・日付が1件も登場しない場合は「年号・日付の記載なし」と明記。

================================================================
【ファクトチェック結果】
================================================================

【✅ 確認済み・正確な情報】
...

【⚠️ 注意・議論あり】
...

【❌ 誤り・修正が必要】
（自動修正済みのためここは空欄になるはず）

【総評】
...

================================================================
【英語 QA】
================================================================

以下をチェックし、問題があれば記載する（問題なければ各項目「✅ 問題なし」）：

【用語チェック】
- "dynasty" の誤用（豊臣・徳川など天皇家以外への使用）→ clan / regime / house を推奨
- "shogun" / "emperor" / "lord" の混同
- 最上級（greatest / most powerful）の過度な多用

【文法・スペルチェック】
- アポストロフィ抜け（Japan's / Tokugawa's 等）
- 動詞の時制ゆれ（過去形と現在形の混在）
- 明らかな typo

================================================================
【画像プロンプト QA】
================================================================

以下をチェックし、問題があれば記載する（問題なければ各項目「✅ 問題なし」）：

【重複・類似チェック】
- 同一または非常に似た構図・キーワードのプロンプトが複数ないか
- 特に冒頭シーンと終盤シーンで同じキャラクターの似た構図が被っていないか
  （例：幸村が冒頭にも終盤にも同じ姿で登場すると「reveal」の演出が弱まる）

【歴史的視覚表現チェック】
- 実在武将の象徴的装備を image_prompt に明示しているか
  例: 真田幸村 → 六文銭 / 鹿角兜、徳川家康 → 葵紋、豊臣秀吉 → 桐紋
- ヨーロッパ風の城・建築を誤って指定していないか
- 画像内にテキスト・文字を描かせる指示が含まれていないか（AI生成は文字が崩れる）

================================================================
【各シーンのナレーション】
================================================================

▶ S{id:02d}  [{type}]  キャラクター: {character_ref or —}  語数: 約{word_count}語（推定実尺: 約{estimated_seconds}秒）
※ 推定実尺 = word_count ÷ 90語/分 × 60 + 1.5s（NARR_DELAY+NARR_TAIL）。hook/teaser/outro は短め。

  【EN】
  {narration}（自動修正済みの場合は修正後のナレーション）

  【JA】
  {日本語訳}

----------------------------------------
... （全シーン繰り返し）

================================================================
【YouTube メタデータ】
================================================================

▼ YouTube 説明文（英語）
{youtube_description}

▼ タグ
{youtube_tags をカンマ区切り}

================================================================
【確認・承認】
----------------------------------------
□ 内容確認完了
□ ファクトチェック・QA問題なし（❌自動修正済み）
□ BGM選択完了
□ 動画生成GO

備考:

================================================================
```

**Google Drive への保存はこの時点では行わない。**

---

### STEP 3B — サムネイル画像（Claudeが直接生成）

エピソードJSONの `thumbnail_prompt` にテキストオーバーレイ指示を加えてGeminiで生成し、`~/Desktop/SC/` に保存する。

**テキストオーバーレイ指示（プロンプトに追記）:**
```
Bold text overlay at the top in large white block letters with dark drop shadow: "{EPISODE_TITLE_SHORT}".
Smaller text at the bottom in white: "{SUBTITLE}".
Text must be clearly legible, sharp, and properly spelled.
Modern cinematic concept art style, dramatic lighting, film production illustration quality. 16:9 aspect ratio, 1280x720.
```

- `EPISODE_TITLE_SHORT`: エピソードの**肩書き・ドラマチックな形容**を大文字で（例: "THE GOD OF WAR" / "THE EXILE" / "THE WRONG SIDE"）
  - ❌ 避ける: 人物名そのまま（"ISHIDA MITSUNARI" / "SASAKI KOJIRO"）
  - ✅ 良い例: "THE GOD OF WAR"（上杉謙信）/ "THE EXILE"（西郷隆盛）/ "THE WRONG SIDE"（石田三成）
- `SUBTITLE`: サブコピー（例: "Japan's Greatest Betrayal"）

**生成コード:**
```python
from google import genai
from google.genai import types
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
response = client.models.generate_content(
    model="gemini-3.1-flash-image-preview",
    contents=full_prompt,
    config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
)
# inline_data から PNG をデスクトップに保存
# 保存先: ~/Desktop/SC/ep{NNN}_thumbnail.png
```

**Google Drive への保存はこの時点では行わない。**

---

### STEP 3C — BGM 3曲構成（役割別: Freesound 3曲 + ライブラリ 6曲 = 計9曲）

本編BGMは**序盤（intro）・中盤（main）・終盤（outro）の3曲構成**（2026-07〜）。
役割ごとに Freesound 新規1曲 + ライブラリ2曲の3候補を用意し、計9曲から各役割1曲ずつ選ぶ
（2026-08-01〜: 12曲/4候補から9曲/3候補に縮小。Freesoundは`orchestral`等の必須キーワードを
含む短い複合クエリだと「No new results」の空振りが非常に多く、さらに拾えてもambient/folk/
アコースティックギター主体など重厚オーケストラ規定に反する曲が多数で、役割2曲を埋めるのに
何度も再試行が必要だった。一方ライブラリ曲は過去の音声QA実績があり信頼度が高いため、
Freesoundは1曲/役割に抑えて再試行コストを下げ、ライブラリの比率を高めた）。
`sc_video_gen.py` がシーンタイプから切り替え時刻を自動計算してクロスフェードでつなぐ。

**役割とトーンの対応:**

| 役割 | 対象シーン | トーン | クエリ例 |
|---|---|---|---|
| intro（序盤） | hook〜setup | 緊張・導入・影 | `"dark tense orchestral"` |
| main（中盤） | rising_action〜climax | 高揚・戦闘・英雄 | `"epic heroic orchestral"` |
| outro（終盤） | falling_action〜outro | 余韻・荘厳・鎮魂 | `"emotional cinematic orchestral"` |

#### ① Freesound から役割別に3曲（各役割1曲）ダウンロード

エピソードのムードを踏まえ、上の表を軸に役割別クエリを3本生成する
（クエリは例。エピソードのムードに応じて調整してよい）。

**クエリ生成ルール:**
- 必ず短く（2〜3語）
- **必ず `orchestral` または `epic` または `cinematic` のいずれかを含める**
- トーン修飾語（組み合わせて使う）: dramatic, heroic, dark, powerful, epic, tense, triumphant, emotional, somber
- 楽器補強（単体では使わない）: strings, brass, choir, taiko, percussion
- **禁止キーワード:** shamisen 単体, piano 単体, ambient, meditation, acoustic, folk, traditional, nature, forest, rain, calm, relaxing, light

**重要:** `--library $HOME/samurai-chronicles/bgm_library.json` を必ず指定する。
これにより、Samurai Chronicles の `bgm_library.json` に既に登録済みの曲（曲名が一致するもの）は
Freesound から再ダウンロードされず自動的にスキップされる（ランプの独り言と同じ仕組み）。

`freesound_download.py` は1回の呼び出しで最大3クエリまで受け付けるため、1回で完結する：

```bash
mkdir -p "$HOME/Desktop/SC/BGM"

FREESOUND_API_KEY=$FREESOUND_API_KEY python3 $HOME/lamp-whisper/freesound_download.py \
  "<Q_intro>" "<Q_main>" "<Q_outro>" \
  "$HOME/Desktop/SC/BGM/" \
  --round 0 --start-slot 1 \
  --library "$HOME/samurai-chronicles/bgm_library.json"
```

**部分失敗時（0件・404・オフトーン判定）:** 失敗したスロットのみ `--start-slot <N>` で
別クエリに差し替えて補完する（スロット番号がずれても、後述のリネーム時に正しい役割の
プレフィックスを付ければ問題ない）。同じスロット番号に複数回ダウンロードが走ると
ファイル名が重複せず両方残ることがあるため、不要になった方は都度 `rm` で削除する。

ダウンロード完了後、スロット番号を役割プレフィックスにリネーム：

```bash
cd "$HOME/Desktop/SC/BGM"
# スロット1=intro / 2=main / 3=outro
for f in BGM_candidate_01_*; do mv "$f" "intro_${f#BGM_}"; done 2>/dev/null
for f in BGM_candidate_02_*; do mv "$f" "main_${f#BGM_}"; done 2>/dev/null
for f in BGM_candidate_03_*; do mv "$f" "outro_${f#BGM_}"; done 2>/dev/null
```

**⚠️ credit.txt の実際の保存先（2026-08-01〜判明・重要）:** `freesound_download.py`
（lamp-whisper由来の共有スクリプト）は CC BY 曲のクレジットテキストを
`$HOME/Desktop/SC/BGM/` には**書き出さない**。常に固定パス `/tmp/lw_bgm_credits/` に
`BGM_candidate_NN_{soundid}_{name}.credit.txt` として保存する（プロジェクト非依存の
共有先のため、他エピソードや別プロジェクトの残骸が混在していることがある）。
STEP 3C の時点ではまだ移送せず、STEP 4 で最終選定した3曲の分だけ
`/tmp/lw_bgm_credits/` から `/tmp/sc_bgm_credits/` へ正しいファイル名でコピーする
（詳細は STEP 4 参照）。

**ライセンスバージョン表記のバグに注意:** 同スクリプトは検索結果に実際のライセンスバージョン
（例: `by/3.0`）を表示するにもかかわらず、credit.txt 本文には常に `CC BY 4.0` と固定で
書き込む。ダウンロード時のコンソール出力（`[by/X.0]` の部分）を必ず確認し、3.0 表記
だった場合は credit.txt の内容を `CC BY 3.0` に手動で修正してから STEP 4 のクレジット
注入・ライブラリ登録に使うこと。

**音声QA（ボーカル・台詞混入チェック・必須）:**

Freesound候補にはBGMとして不適切な「音声混じり」の曲（ナレーション・台詞・歌詞入りサンプル等）
が紛れることがある。タイトルに `cast` / `voice` / `narration` / `dialogue` / `whisper` 等の
語がないか目視確認するのに加え、`sc_bgm_qa.py` で機械的に検証する（Geminiの音声理解による
自動QA。`sc_image_gen.py` の画像QAと同じ考え方）：

```bash
python3 $HOME/samurai-chronicles/sc_bgm_qa.py --dir "$HOME/Desktop/SC/BGM"
```

QAの `details` に含まれる楽器編成の説明も確認し、`has_vocals: true`（ボーカル混入）だけでなく
`ambient` / `acoustic guitar 主体` / `folk` / `rock` など「重厚なオーケストラ調」から外れる
編成が疑われる場合も、そのスロットだけ `--start-slot <N>` で別クエリに差し替えて再ダウンロード
→ 再度QAを実行する。全候補が「ボーカルなし・オーケストラ調」になるまで②以降には進まない。

#### ② ライブラリから役割別に6曲（各役割2曲）選択

`bgm_library.json` を読み込み、各役割のトーンに合うタグの曲を2曲ずつ選ぶ
（intro=dark/tense系、main=epic/heroic系、outro=emotional/somber系。
エピソードのタイトル・シーン構成も考慮し、同一役割の2曲は極力タグ・雰囲気が
被らないものを選ぶ）。

選んだ6件を `~/Desktop/SC/BGM/` にコピー（試聴用の一時コピー。選択後は削除）：

```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles"
cp "$DRIVE/<path1>" "$HOME/Desktop/SC/BGM/intro_library_01_<lib_id>.mp3"
cp "$DRIVE/<path2>" "$HOME/Desktop/SC/BGM/intro_library_02_<lib_id>.mp3"
cp "$DRIVE/<path3>" "$HOME/Desktop/SC/BGM/main_library_01_<lib_id>.mp3"
cp "$DRIVE/<path4>" "$HOME/Desktop/SC/BGM/main_library_02_<lib_id>.mp3"
cp "$DRIVE/<path5>" "$HOME/Desktop/SC/BGM/outro_library_01_<lib_id>.mp3"
cp "$DRIVE/<path6>" "$HOME/Desktop/SC/BGM/outro_library_02_<lib_id>.mp3"
```

※ `<lib_id>` はライブラリエントリの `id`（例: `ep003-BGM`）。STEP 4 で id 逆引きに使うため正確に。

`~/Desktop/SC/BGM/` に計9曲が並ぶ（役割ごとに新規1曲・ライブラリ2曲の3候補）：
```
intro_candidate_01_xxx.mp3   ← Freesound 新規（序盤）
intro_library_01_xxx.mp3     ← ライブラリ（序盤 1）
intro_library_02_xxx.mp3     ← ライブラリ（序盤 2）
main_candidate_02_xxx.mp3    ← Freesound 新規（中盤）
main_library_01_xxx.mp3      ← ライブラリ（中盤 1）
main_library_02_xxx.mp3      ← ライブラリ（中盤 2）
outro_candidate_03_xxx.mp3   ← Freesound 新規（終盤）
outro_library_01_xxx.mp3     ← ライブラリ（終盤 1）
outro_library_02_xxx.mp3     ← ライブラリ（終盤 2）
```

---

### サムネイル・BGMのユーザー確認（2026-07-28〜）

サムネイル・BGMは**ユーザーに提示し、明示的なOKを得てから次に進む**（2026-07-28〜変更。
以前はどちらも自動確定していたが、最終判断はユーザーに委ねる運用にした。シーン画像の
確認はSTEP 5Cで別途行う）。

**サムネイル:**
- 生成後、Claude が Read ツールで画像を直接見て一次チェックする（文字の可読性・時代考証・破綻の有無）。明らかな問題（文字化け・崩れた構図等）があれば1回だけ自動再生成する。
- そのうえで Read ツールで画像をチャットに表示し、ユーザーの確認を待つ。差し替え希望があれば再生成する。

**BGM:**
- 役割別9曲（各役割3候補: Freesound新規1 + ライブラリ2）を用意した後、Freesound新規候補には
  `sc_bgm_qa.py` で音声QA（ボーカル・台詞混入チェック＋オーケストラ純度チェック）を実行し、
  問題があれば該当スロットのみ別クエリで再取得する。
- `/consult` スキルを使い、エピソードのトーン・3曲構成の制約（役割ごとに固定音量ループ、
  曲間はクロスフェード4秒、序盤→中盤→終盤で緊張→高揚→余韻の流れを作る）を踏まえて
  **9曲から各役割1曲ずつ計3曲**に絞り込む。この時点の `/consult` はテキスト対話
  （曲の特徴・タグ・使用履歴の説明ベース）であり、実音声は聴いていないことに留意する。
- **選定3曲が確定したら、選ばれなかった曲を `~/Desktop/SC/BGM/` から削除して3曲のみ残し、
  `sc_bgm_final_check.py --episode ep{NNN}` を実行する（2026-08-01〜）。**
  このスクリプトは選定3曲の実音声と STEP 3A で生成済みの `ep{NNN}_制作確認書.txt` 全文を
  Gemini のマルチモーダル音声理解に渡し、「重厚なオーケストラ調」方針への適合・各曲のトーンと
  対応シーン群の内容との一致・3曲を通した緊張→高揚→余韻の流れの破綻有無・音質面の懸念を
  実音声ベースで最終検証する（`/consult` のテキストのみの判断を補完するステップ）。
- `sc_bgm_final_check.py` の判定結果（各曲評価＋総合GO/差し替え推奨）を、
  ユーザーへの提示メッセージに含める。
- **選定3曲を `~/Desktop/SC/BGM/` から `~/Desktop/SC/`（直下）にコピーし、`open` コマンドで
  `~/Desktop/SC/` を Finder に開いて、ユーザー自身に試聴してもらった上でOKを得る**
  （2026-08-01〜。`~/Desktop/SC/BGM/` のサブフォルダの中に開くより、制作確認書・サムネイルと
  同じ階層に3曲だけ並べた方が確認しやすいとのフィードバックを反映。SendUserFileはmp3を
  インラインプレビューできないため使わない）。
  ここは自動確定せず、明示的な承認を待って初めて次に進む。
- OKが出るまで STEP 4（BGM紐付け・Google Driveへの移動）には進まない。
- OK後、`~/Desktop/SC/` 直下にコピーした3曲は削除する（`~/Desktop/SC/BGM/` 内のオリジナルは
  STEP 4 のBGM登録処理で使うため残す）。
- 差し替え希望があれば該当役割のみ再選定（別候補への切替、または新規クエリで再検索）し、
  再度 `sc_bgm_final_check.py` → Finder試聴の順で確認を求める。
- OK後、使用しなかった credit.txt を削除する。

### 完了報告

制作確認書のファクトチェック・QA結果を画面に表示する。サムネイル・BGMは上記の通り
ユーザー確認が必須なので、この報告と合わせて（またはこの直後に）提示しOKを得る。

**⚠️ 重要: TTS・画像生成（STEP 5A/5B）はユーザーの承認が取れるまで絶対に開始しない。**
ナレーション修正が必要な問題がある場合、承認前にTTSを走らせると再生成が必要になる。

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 ファクトチェック・QA 結果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌自動修正済み（{N}件）:
  🔧 S05: "1582年" → "1600年" に修正（ep.json 更新済み）
  🔧 S03: "Toyotomi dynasty" → "Toyotomi clan" に修正済み

⚠️ 要確認（{N}件）:
  ⚠️ S07: "Japan's most powerful" → 最上級の多用（S02・S11 と重複）

✅ 年号・日付: 全件確認済み
✅ 文法・スペル: 問題なし
✅ 画像プロンプト: 問題なし
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

❌自動修正済み・⚠️なし → 「✅ QA完了 — 問題なし」を表示。ナレーション面はここで確定するが、
STEP 4 へは**サムネイル・BGMのユーザー確認が取れてから**進む（自動では進まない）。
⚠️がある場合は内容を表示し、ナレーション修正確認とサムネイル・BGM確認をまとめてユーザーに求めてよい。

---

### 確認・修正ループ

ユーザーの回答に応じて対応する：

- **ナレーション修正あり（❌ / ⚠️）** → `episodes/ep{NNN}.json` の該当シーンを直接編集して修正。`~/Desktop/SC/ep{NNN}_制作確認書.txt` も上書き更新。修正箇所を報告して再確認を求める。
- **サムネイルを見直したい** → 再生成して再度提示する。
- **BGMを見直したい** → 該当役割を再選定（別候補への切替、または新規クエリで再検索）し、再度試聴確認を求める。
- **すべてOK（ナレーション・サムネイル・BGM）** → STEP 4 へ進む

---

## STEP 4 — Google Driveへ移動

すべてOKが取れたら、デスクトップのファイルをGoogle Driveエピソードフォルダへ移動する：

```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}"
mkdir -p "$DRIVE/audio"

# 制作確認書を移動
mv "$HOME/Desktop/SC/ep{NNN}_制作確認書.txt" "$DRIVE/"

# サムネイルを移動
mv "$HOME/Desktop/SC/ep{NNN}_thumbnail.png" "$DRIVE/"

# 役割ごとに残った1曲を判定して登録: Freesound新規 or ライブラリ
mkdir -p /tmp/sc_bgm_credits
for ROLE in intro main outro; do
  CHOSEN=$(ls "$HOME/Desktop/SC/BGM/${ROLE}_"*.mp3 2>/dev/null | head -1)
  if [ -z "$CHOSEN" ]; then
    echo "⚠️ ${ROLE} のBGMが見つかりません"; continue
  fi
  CHOSEN_STEM=$(basename "$CHOSEN" .mp3)

  if [[ "$CHOSEN" == *"_candidate_"* ]]; then
    # ⚠️ 順序が重要: sc_bgm_library.py --add は呼び出し時点で
    # /tmp/sc_bgm_credits/{stem}.credit.txt の有無を見てライセンスを CC0/CC BY 判定する。
    # credit.txt を先に正しい名前で用意してから --add を呼ぶこと（逆順だとCC0登録されて
    # 後から手直しが必要になる）。
    # SOUND_ID はファイル名の "_candidate_NN_{SOUND_ID}_" 部分から抽出する
    SOUND_ID=$(echo "$CHOSEN_STEM" | sed -E 's/^[a-z]+_candidate_[0-9]+_([0-9]+)_.*/\1/')
    SRC_CREDIT=$(ls /tmp/lw_bgm_credits/*_"${SOUND_ID}"_*.credit.txt 2>/dev/null | head -1)
    if [ -n "$SRC_CREDIT" ]; then
      cp "$SRC_CREDIT" "/tmp/sc_bgm_credits/${CHOSEN_STEM}.credit.txt"
      # ライセンスバージョンが CC BY 3.0 等だった場合、STEP 3C の時点で
      # /tmp/lw_bgm_credits 側を修正済みのはず。念のためここでも内容を確認してよい。
    fi

    # Freesound新規: BGM/{ep}-BGM-{role}.mp3 へ移動し bgm_sources[role] を設定
    python3 $HOME/samurai-chronicles/sc_bgm_library.py \
      --add --episode ep{NNN} --role "$ROLE" --file "$CHOSEN" \
      --stem "$CHOSEN_STEM"
  else
    # ライブラリ既存曲: bgm_sources[role] にパスを記録、ファイルは移動しない
    python3 $HOME/samurai-chronicles/sc_bgm_library.py \
      --use-library --episode ep{NNN} --role "$ROLE" --stem "$CHOSEN_STEM"
    rm -f "$CHOSEN"
  fi

  # クレジット注入（CC BY の場合。sc_inject_bgm_credit.py は重複追加しないので役割ごとに実行してよい）
  CREDIT="/tmp/sc_bgm_credits/${CHOSEN_STEM}.credit.txt"
  if [ -f "$CREDIT" ]; then
    python3 $HOME/samurai-chronicles/sc_inject_bgm_credit.py \
      --episode ep{NNN} --credit-file "$CREDIT"
  fi
done

# ライブラリ登録後、--add 呼び出し時点で license が CC0 のまま登録されていないか
# bgm_library.json を確認する（credit.txt の検出漏れがあった場合のフォールバック）。
# 該当エントリがあれば license を "CC BY"・credit を正しい文言に手動修正する。

# /tmp の残 credit.txt をすべて削除
rm -f /tmp/sc_bgm_credits/*.credit.txt

# デスクトップの SC/ フォルダを削除（thumbnail・制作確認書は mv 済み、BGM残骸も含め一括削除）
rm -rf "$HOME/Desktop/SC"
```

credit.txt が存在した場合（CC BY）は、制作確認書の BGM 欄を更新する：
- BGM タイトル・作者名
- Freesound URL（`https://freesound.org/s/{SOUND_ID}/`、SOUND_ID はファイル名から取得）
- ライセンス（実際のバージョンを確認して記載。credit.txt の文言が常に「CC BY 4.0」固定に
  なっている既知のバグがあるため、STEP 3C のダウンロード時コンソール出力の `[by/X.0]` と
  必ず突き合わせる）
- 概要欄に貼るクレジットテキスト（`🎵 Music: ... by ... (freesound.org) — CC BY {version}`）

BGM が CC0 の場合は「CC0 — クレジット不要」と記載。

**更新後の BGM 欄フォーマット（3曲構成）:**
```
BGM           : ✅ 3曲構成
  序盤 (intro) : {タイトル} by {作者名} [CC0 / CC BY 4.0]
  中盤 (main)  : {タイトル} by {作者名} [CC0 / CC BY 4.0]
  終盤 (outro) : {タイトル} by {作者名} [CC0 / CC BY 4.0]
```
CC BY の曲がある場合は、その曲ごとに Freesound URL と概要欄クレジット行を続けて記載する。

Freesound の SOUND_ID は BGM ファイル名（`BGM_candidate_XX_{SOUND_ID}_...mp3`）から取得する。

移動完了を報告する。

---

## STEP 5A/5B — 素材を自動生成する

STEP 5A（TTS）と STEP 5B（画像）を並行して実行する。
**STEP 5Bの画像生成は3コマンドを並行実行してはいけない** — `--shorts` は本編(16:9)の
画像を流用して9:16に再構成する仕組み（2026-08-02〜、コスト削減のため）のため、
必ず本編用（引数なし）を先に完走させてから `--shorts` を実行する（`--face` は
本編画像に依存しないため並行可）：

```bash
# STEP 5A — TTS生成（並行可）
python3 sc_tts_gen.py --episode ep{NNN}                    # ナレーション音声生成（本編用・シーンタイプ別感情トーン）
python3 sc_tts_gen.py --episode ep{NNN} --teaser           # トレイラーイントロTTS生成（S00_teaser.wav）
python3 sc_tts_gen.py --episode ep{NNN} --shorts           # Shorts専用TTS生成（S00_shorts.wav）

# STEP 5B — 画像生成（--face はここと並行してよいが、--shorts は本編完了後に実行）
python3 sc_image_gen.py --episode ep{NNN}                  # 本編用画像生成（16:9）
python3 sc_image_gen.py --episode ep{NNN} --face           # Shorts冒頭顔アップ画像生成（S00_face.png、本編と並行可）
# ↓ 本編(16:9)完了後に実行 — QA承認済みの本編画像を9:16に再構成する（新規生成しない）
python3 sc_image_gen.py --episode ep{NNN} --shorts         # Shorts用画像生成（9:16）
```

---

## STEP 5C — 画像QA結果の確認・ユーザー確認（2026-07-28〜: 目視確認を追加）

STEP 5A/5B 完了後、zoom_anchor 判定の**前**に実施する。画像の再生成が発生しうる工程を
先に終わらせてから zoom_anchor を判定することで、再生成後の構図とズレた座標を書いてしまう
手戻りを防ぐ。

### ⚠️ 絶対ルール

- まず `image_qa_result.json` / `image_qa_result_shorts.json` / `image_qa_result_face.json`
  （`--face` 使用時のみ）を読み、`sc_image_gen.py` が生成時に Gemini Vision で行った
  自動チェック結果（2段階リトライ済み）を確認する。
- このステップで修正できる手段は**画像の再生成のみ**（`image_prompt` フィールドの修正含む）。
  ナレーション本文・その他のJSONフィールドの修正は一切提案しない（＝TTS再生成は絶対に発生させない）。
  ナレーションの品質はSTEP 3Aで保証済みとみなす。
- QAの自動チェック（`all_ok`）が通っても、それだけでは STEP 5D・STEP 6 には進まない。
  下記の通り、必ずユーザーが実際に画像を見て確認した上でOKを得る（2026-07-28〜）。

### 自動リトライの仕組み（`sc_image_gen.py` 内で完結）

各シーンの生成は、`sc_image_gen.py` 内部で以下の2段階まで自動的に試行される
（Claude が手動でプロンプトを書き換えて再実行する必要はない）：

1. **1回目**: 元のプロンプトで生成
2. **2回目**（QA失敗時）: 検出された issue の原文＋種類（TEXT / ARCHITECTURE / DISTORTION / MISMATCH）
   に応じた具体的な修正指示を自動でプロンプトに追記して再生成

2回試行してもQAが通らなかった場合のみ、そのシーンは `warnings` に残る。
つまりこの STEP で読み込む `image_qa_result*.json` は**すでに機械的な自動修正を尽くした後の
最終結果**であり、残っている WARNING はここから先はClaudeが実際に画像を見て判断する
（下記「WARNINGへの一次対応」）。

**2026-08-02改訂（コスト削減）:** 実績データ（89エピソード分のQA結果）で、3回目まで
リトライしても最終的にNGのまま終わるケースが本編38.5%・Shorts39.1%と高頻度で、
3回目の追加コストに見合う改善効果が確認できなかったため、最大試行回数を3→2回に削減した。
また `--shorts` は本編(16:9)でQA承認済みの画像をGeminiに渡して9:16に再構成する方式に変更し、
ゼロからの独立生成をやめた（同じ内容を2回課金する無駄と、独立生成時のMISMATCH再発を防ぐ）。
各 `image_qa_result*.json` には `scene_attempts`（シーンごとの試行回数ログ）が追加されており、
リトライ回数の妥当性は今後この値の推移で検証する。

### チェック内容

Google Drive の以下のファイルを読み込む：
```bash
cat ~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}/image_qa_result.json
cat ~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}/image_qa_result_shorts.json
# --face を使用した場合のみ:
cat ~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}/image_qa_result_face.json
```

各JSONの `all_ok` を確認する：
- `all_ok: true` → 問題なし
- `all_ok: false` → `warnings` 配列に `{scene_id, issues}` が入っている（＝2回試行済みで解決しなかったシーン）

### WARNINGへの一次対応（Claude判断、2026-08-02〜）

`warnings` に残ったシーンは、ユーザーに見せる前に**まずClaudeが判断・対応する**
（自動2回リトライは機械的な修正なので、次はClaudeが実際に画像とissueを見て判断する）。
各WARNINGシーンについて、Read ツールで実際の画像を直接見て、issueの内容と照らし合わせる：

1. **許容できると判断した場合** → そのシーンは解決済み扱いとし、ユーザーには諮らない
   （最終目視確認STEPで他の画像と同様に見てもらう機会はある）。
   許容の目安: QAの指摘が軽微・境界的（構図のわずかな解釈違い、遠景の些細なディテール等）で、
   物語の伝達や画面の完成度を損なわないもの。
   許容しない目安: 明確な解剖学的破綻、時代考証違反（現代的な髪型・道具等）、文字/透かしの混入、
   シーン内容と明らかに違う被写体・状況。
2. **許容できないと判断した場合** → Claude自身が該当シーンの `image_prompt` を
   `episodes/ep{NNN}.json` 内で具体的に修正する（issueの内容を踏まえ、自動リトライの
   定型修正より踏み込んだ、その画像固有の修正指示を書く）。修正後、そのシーンのみ再生成する：
   ```bash
   python3 sc_image_gen.py --episode ep{NNN} --scenes N          # 本編シーンの場合
   python3 sc_image_gen.py --episode ep{NNN} --shorts --scenes N # Shortsシーンの場合
   ```
   再生成後の `image_qa_result*.json` を再度確認する：
   - 合格 → 解決済み扱い（ユーザーには諮らない）
   - 不合格 → このシーンのみ次の「アクション」でユーザーに諮る

この一次対応の結果は完了報告にまとめて示す（後述のレポート出力フォーマット参照）。
ナレーション本文や他のJSONフィールドの修正は絶対に行わない（＝TTS再生成は発生させない）。

### レポート出力フォーマット

`all_ok: true`（全ファイル、またはClaudeの一次対応で全件解決）の場合：

```
✅ STEP 5C 完了 — 画像 QA: 全シーン問題なし（自動2回 + Claude一次対応で{N}件解決） → STEP 5D へ進みます
```

そのまま即座に次のステップへ進む。

Claude一次対応後もなお解決しないシーンが残る場合：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  画像 QA — ep{NNN}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  自動2回リトライ後のWARNING: {N}件
  → Claude判断で許容: {N}件 / Claude修正で解決: {N}件
  → 未解決のまま: {N}件
  [未解決] S{N}: {issues の内容}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### アクション

Claudeの一次対応でも解決しなかったシーンのみユーザーに確認：
```
{N}件の画像はClaudeでの修正でも解決しませんでした。
[A] さらにプロンプトを手動調整して再生成
[B] 許容してそのまま zoom_anchor 判定へ進む
```

ナレーション変更の選択肢は絶対に提示しない。
[A] を選んだ場合も同様に `sc_image_gen.py --scenes N,M` で再実行する（自動2段階リトライが走る）。
それでも解決しない場合は、再度ユーザーに許容可否を確認する。

### ユーザーによる目視確認（必須・2026-07-28〜、確認方法は2026-07-28に修正）

自動QA（WARNING対応含む）が完了したら、`images/` フォルダの全シーン画像を
ユーザーに確認してもらう。ファイル保存場所は変更しない（Google Drive上に生成された
ままでよい）— あくまで動画生成に進む前の確認ゲートを追加する。

**⚠️ 表示方法の制約（検証済み）:** 1ターンに画像を配信するツール呼び出し
（`Read` や `SendUserFile`）が複数あると、ユーザー側に表示されない。
Read単体1回のみ・他の画像配信呼び出しなしのターンでのみ表示に成功することを確認済み。
したがって全シーンを一括でReadツールに貼り付ける、または `SendUserFile` で
まとめて送る、という方法は**行わない**。

**2026-07-28〜: A/Bの選択肢を提示せず、最初から Google Drive で直接確認してもらう
方式をデフォルトとする。**

```
シーン画像が生成できました。Google Driveの images/ フォルダ（ep{NNN}/images/）で
ご確認ください。問題なければお知らせください。
```

差し替え希望があれば該当シーンの `image_prompt` を修正して `sc_image_gen.py --scenes N` で
再生成し、再度そのシーン（1枚のみ）を表示して確認を取る。OKが出るまで STEP 5D には進まない。

---

## STEP 5D — シーン画像解析・zoom_anchor 書き込み

STEP 5C（画像QA・再生成含む）が完了し、最終的な画像が確定した後に実施する。
Claude が各シーン画像を直接 Read ツールで読み込み、ズーム焦点座標を判定して
ep{NNN}.json に書き込む。**Gemini API は使わない。Claude のビジョンで直接判断する。**

### 対象シーン（zoom_anchor を書き込む）

- `character_ref` が設定されているシーン（1人構図）
- かつ、image_prompt に "on the left"/"on the right" 系キーワードが **両方** 含まれない（2人構図でない）こと

その他のシーン（character_ref なし、または2人構図）はスキップ（zoom_anchor は null のまま）。

### 手順

1. Google Drive の `images/` フォルダから S{id:02d}.png を Read ツールで読み込む
2. 画像内の主被写体の重心を判断し、正規化座標で記録：
   - `x`: 0.0=画面左端、0.5=中央、1.0=右端
   - `y`: 0.0=画面上端、0.5=中央、1.0=下端
   - 人物の「顔〜胸」あたりの重心を焦点にする（足元や背景ではなく）
3. ep{NNN}.json の該当シーンに `"zoom_anchor": {"x": ..., "y": ...}` を書き込む

### 例

```json
{
  "scene_id": 3,
  "character_ref": "musashi",
  "zoom_anchor": {"x": 0.38, "y": 0.42},
  ...
}
```

### 完了報告

zoom_anchor の処理結果は**画面に表示しない**。サイレントに実行して完了後は次のステップへ進む。

---

## STEP 6 — 動画・字幕を生成する

```bash
python3 sc_video_gen.py --episode ep{NNN}      # 動画生成（本編 + Shorts）
python3 sc_subtitle_gen.py --episode ep{NNN}   # 字幕生成
```

完了後：
```
ep{NNN} の制作が完了しました。

出力ファイル:
  - Samurai Chronicles ep{NNN}.mp4
  - ep{NNN}_shorts.mp4
  - ep{NNN}.srt

動画を確認してから /sc-upload でアップロードしてください。
```

**⚠️ 重要:** STEP 6 完了後はここで必ず停止する。
`sc_sns_up.py` の自動実行・`/sc-upload` の自動呼び出しは絶対に行わない。
アップロードはユーザーが明示的に `/sc-upload` を実行した時のみ行う。
