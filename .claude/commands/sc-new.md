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
| STEP 3A/3B/3C | 制作確認書・サムネイル・BGM選定（並行、確認待ちなし） | 約30〜40分 |
| *(確認待ち)* | ナレーションに⚠️がある場合のみここで確認 | 要確認（まれ） |
| STEP 5A/5B | TTS生成 + 画像生成 16:9（並行） | 約10分 |
| STEP 5A/5B | TTS（teaser・shorts）+ 画像生成 9:16（並行） | 約3分 |
| STEP 5C | 画像QA（＋再生成時 +3〜5分） | 約3〜5分 |
| STEP 5C | シーン確認ページ生成（画像×音声×BGM×日本語訳） | 約1分 |
| *(確認待ち)* | サムネイル・BGM・シーン画像を1回のメッセージでまとめて確認 | 要確認 |
| STEP 4  | Google Driveへ移動・BGM本登録（統合確認のOK後に実行） | 約1分 |
| STEP 5D | zoom_anchor 判定 | 約3〜5分 |
| STEP 6  | 動画生成（本編+Shorts） | 約40〜50分 |
| STEP 6  | 字幕生成 | 約1分 |

**合計目安: 約100〜130分**（確認待ち・再生成除く）
**2026-08-04〜: 確認ポイントを3箇所→実質1箇所に統合**（ナレーション⚠️時のみ例外的に2箇所）。
STEP4（Google Driveへの移動・BGM本登録）はSTEP3完了直後ではなく、STEP5C後の統合確認で
OKが出てから実行する順序に変更した（未承認のBGMをライブラリに本登録してしまうリスクを防ぐため）。
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

**角度（angle）選定の優先度（2026-08-04改訂・Opusによる分析監査を反映）：**

⚠️ 2026-08-02分析の一部は統計的に不十分だったことが2026-08-04の監査で判明した
（サンプルサイズ不足・外れ値ep030への依存・同一事例の重複カウント等）。以下は訂正済みの内容。

- `angle: "overview"`（生涯・人物像の全体像）は**維持率で優位**が複数の対比で確認できる
  （overview vs military +3.21t, vs character +2.34t）。CTRの優位はep030 1本への依存が大きく
  単独では弱い根拠だが、維持率目的では引き続き優先してよい。
- `"death"`（死の謎）を抑制する2026-08-02のルールは**撤回する**。根拠だったep046/047の
  2本は「疑問形タイトル」「有名人物の死因ミステリー」とも完全に同一の事例で、実質n=2
  （3つの独立した悪材料に見えたのは1事例の三重カウント）。death角度自体を避ける理由はない。
- `"key_event"`（単一事件の顛末）を機械的に減らす必要はない（overview比でCTR・維持率とも
  統計的な有意差なし）。ただし実測で維持率がやや低めの傾向はあるため、**「事件の顛末」
  ではなく「その事件を通した人物の生き方・選択」を軸にする**構成上の工夫は引き続き有効。
- **新知見（2026-08-04・統計的に最も信頼できる結果）: 忍者・間諜テーマが極めて強い。**
  該当7本（ep020, 027, 035, 050, 063, 064, 065）が**7本とも**CTR中央値超え
  （平均CTR 4.06% vs 全体3.10%、偶然の確率0.8%未満）。**積極的に追加すべき。**
  ただし維持率は平均以下の傾向があるため、CTRで惹きつけた後に飽きさせない構成
  （謎解き・人物ドラマの軸を持たせる）を意識すること。

**人物選定の優先度（2026-08-04改訂）：**
- 知名度による効果（マイナー人物が有利）は分類ルール次第で0.19〜0.88ptと変動し、頑健な
  根拠ではないことが判明した。**「マイナー人物のみ」に固定するルールは緩和する。**
  現在のpendingキューが有名人物0件・マイナー100%という偏った構成になっており、これでは
  知名度仮説自体を今後も検証できない。**新規提案では有名人物（信長・家康・秀吉・武蔵・
  信玄・謙信・西郷等）を意識的に3〜4本混ぜ、仮説を検証可能な状態に戻す。**
  有名人物は検索流入の受け皿にもなる。
- **「知られざる軍師・参謀」タイプは実データで再現した数少ない信頼できるシグナル**
  （黒田官兵衛: ep030 CTR9.77%・ep052 CTR6.02%でCTR1位・2位を同一人物が独占）。
  竹中半兵衛・山本勘助・直江兼続など同系統（主君を支える策士・二番手のブレーン）の
  人物は引き続き積極的に候補へ入れる。

**era（時代区分）の偏りに注意（2026-08-04追加）:** Bakumatsu期の実績データはep068の1本
（CTR0.6%）しかなく、傾向を判断できる材料がない。pendingキューには2026-08-04時点で
Bakumatsu系が5件あるが、**まとめて連続投入せず、2〜3本公開して初期データ（公開後14日CTR。
`/sc-analytics`の年齢調整済み指標を参照）を確認してから残りの優先度を判断する**こと。
他のeraで同様に実績データが乏しい区分（Heian・Meiji・Kamakura等）も同様の注意を払う。

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

### 生成方法（2026-08-04〜: 生成はSonnet・チェックはOpusの二段構成に変更）

このSTEPの生成（エピソードJSON全体の作成）は `Agent` ツールで **model指定なし**
（デフォルト＝Sonnet相当）のサブエージェントに任せる。

**経緯:** 2026-07-28、ep068制作中にSonnetの史実知識不足に起因する複数の誤り（龍馬の髪型・
ブーツの着用時期・実在人物の甲冑有無等）が発覚し、一時は生成・チェック両方をOpusに委任していた。
しかし週5本ペースでOpusサブエージェントを2回/話（STEP 2A生成＋STEP 3Aチェック）呼ぶと
Claudeの利用上限を頻繁に消費してしまうため、2026-08-04に**生成はSonnet・史実チェックは
STEP 3AのOpusに一本化**する構成へ変更した。STEP 3Aは`episodes/ep{NNN}.json`を直接修正できる
権限を持つため、実質的な精度担保はSTEP 3Aが担う（下記STEP 3A参照）。さらに下流の
画像生成QA（Gemini Vision、ARCHITECTURE=時代考証違反を検出）とSTEP 5Cの
Claude一次判断でも時代考証ミスを拾える多層構成になっている。
**この変更後1〜2話は、ep068のような史実知識ミスが再発していないか特に注意して確認すること。**

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

**実績データに基づく優先度（2026-08-04改訂・訂正版）:** 型A/D「The X Who/That〜」は
型B「Why〜」より**維持率が優位**（複数回の分析で再現している頑健なシグナル。直近では
型A/D単独 vs それ以外全体で t≈2.9・統計的に妥当な差）。この点は**引き続き維持率目的で推奨する**。

⚠️ 訂正: 2026-08-02の分析で「型A/DのCTR優位が逆転して消滅した」としていたのは
**分析コード側のバグによるアーティファクトだった**（`sc_yt_analyze.py`の集計スクリプトが
リタイトル済み動画を現在のタイトルで分類しており、リタイトル前に稼いだインプレッションの
大半が新ラベルに誤って帰属していた。2026-08-04に修正済み）。正しく分類し直すと、
型A/DとBのCTRは元々ほぼ差がない（優位も逆転もしていない）。**CTRを理由に型A/Dを推奨も
否定もしない**、というのが正確な現状認識。型Bは「なぜ」の答えが動画内に明確にある場合に使う。
なお型の効果は下記「登場人物数」と交絡しており、**より根本的なのは
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

**登場人物数の上限（2026-08-04改訂: CTR施策から制作品質の指針に格下げ）:**

⚠️ 訂正: これまで「1人構成がCTRを押し上げる」という強い実績データ根拠があるとしてきたが、
2026-08-04の監査で、外れ値ep030を除外すると差が統計的に非有意になり、しかも
`character_ref`のユニーク数は「物語の主役の人数」ではなく「登場する画像アセットの種類数」の
代理指標に過ぎない（脇役が名前付きキャラクターとして描かれるかどうかで変わる）ことが判明した。
維持率では**逆に**2人構成の方が高い傾向もあり、CTR施策としての根拠は弱い。

- エピソード全体を通して `character_ref` に設定する**人物は最大2人まで**は引き続き推奨する。
  ただし理由はCTR最大化ではなく、**画像生成の一貫性・制作コストの制御**（キャラクター参照が
  増えるほど`characters/`定義の管理と画像プロンプトの整合性維持が煩雑になるため）
- 対抗者・裏切り者など2人目までは許容するが、3人目以降は
  `character_ref: null` のまま「シルエット」「a rival general」等の匿名描写にとどめる
- 「主人公1人・1つの選択」への絞り込みは、CTR施策としてではなく**物語構成上の指針**
  （焦点が明確な方が構成しやすい）として引き続き推奨する

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
サブエージェントに任せる（史実知識の精度のため）。Agentプロンプトには
`episodes/ep{NNN}.json` のパスと、以下の手順・フォーマット全文を含める。
`run_in_background: false` で結果を待つ。ファクトチェックで❌が見つかった場合の
`episodes/ep{NNN}.json` 直接修正も含めてサブエージェントに行わせてよい
（オーケストレーターは完了報告のみ受け取り、必要ならファイルの整合性を軽く確認する）。

**2026-08-04〜: STEP 2Aの生成がSonnetに戻ったため、このSTEP 3Aが史実知識の精度を
担保する唯一のOpusチェック層になった。** 下記【歴史的視覚表現チェック】の各項目は
特に厳密に確認すること（ep068で実際に見逃された種類の誤りのため）。

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
- **髪型が人物・時代に対して正確か**（例: 幕末以降の人物にちょんまげを強制していないか、
  逆に江戸期以前の人物に散切り頭等の後代の髪型を指定していないか）
- **服装・装備の着用時期が史実と合っているか**（例: ブーツ・洋装は幕末以降の一部人物のみ、
  それ以前の時代設定で誤って指定していないか）
- **甲冑の有無が人物・場面設定と合っているか**（実在武将でも平時・私的な場面では甲冑なしが
  正しい場合がある。逆に合戦場面で甲冑なしを指定していないか）
- **一般に知られる容貌イメージとの整合（2026-08-25〜追加）**: 主人公が肖像画・写真・銅像等の
  資料が残っている、または広く知られたイメージが確立している人物の場合、`characters/{name}.txt`
  の容姿設定が「時代考証的に正しいだけの一般的な武士／学者」の記述に留まっていないか確認する。
  `WebSearch` で「{人物名} 肖像 写真 銅像 容姿 特徴」等を検索し、以下を調べる：
    - 実際の写真が現存するか（幕末〜明治期の人物は現存する場合がある）
    - 現存しない場合、後年描かれた肖像画（例: エドアルド・キヨッソーネによる西郷隆盛・大村益次郎の
      肖像画は、いずれも本人を知る関係者の証言をもとに没後に描かれた想像画であり、実写ではない
      ことに留意する — 「広く知られたイメージ」＝「史実の写実」とは限らない）
    - 同時代人の証言に基づく体格・顔立ちの具体的特徴（身長、体格、顔の輪郭、目・鼻・眉の特徴、
      特徴的な髪型・装身具等）
  こうした資料が見つかった場合、判明した具体的特徴を `characters/{name}.txt` と
  `thumbnail_prompt` / `shorts_face_image_prompt` に反映する（Sonnetによる STEP 2A 生成では
  この種の実在人物の個別的な容貌調査までは行われないため、STEP 3A のこのチェックで補う）。
  該当する資料が見当たらない人物（記録の乏しいマイナー武将等）は、時代考証に基づく一般的な
  容姿設定のままでよい。

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

### サムネイル・BGMの生成・自動チェック（確認は後段に統合、2026-08-04〜）

サムネイル・BGMは**ユーザーに提示し、明示的なOKを得てから次に進む**という方針自体は
2026-07-28から変わらないが、**確認を求めるタイミングはSTEP 5C（画像QA）完了後まで遅らせる**
（2026-08-04〜。以前はSTEP3完了直後にサムネイル・BGM、STEP5C後にシーン画像、と最大3回に
分かれていた確認を1回に統合するため。サムネイル・BGM自体はTTS/画像生成の前提ではないため、
確認を遅らせてもSTEP5A/5B以降が無駄になることはない）。ここでは生成と自動チェックのみ行い、
ユーザーへの提示・確認待ちは行わない。

**サムネイル:**
- 生成後、Claude が Read ツールで画像を直接見て一次チェックする（文字の可読性・時代考証・破綻の有無）。明らかな問題（文字化け・崩れた構図等）があれば1回だけ自動再生成する。
- ユーザーへの表示・確認は行わない。`~/Desktop/SC/ep{NNN}_thumbnail.png` に保存したまま次に進む。

**BGM:**
- 役割別9曲（各役割3候補: Freesound新規1 + ライブラリ2）を用意した後、Freesound新規候補には
  `sc_bgm_qa.py` で音声QA（ボーカル・台詞混入チェック＋オーケストラ純度チェック）を実行し、
  問題があれば該当スロットのみ別クエリで再取得する。
- Claude（オーケストレーター自身）が、エピソードのトーン・3曲構成の制約（役割ごとに固定音量ループ、
  曲間はクロスフェード4秒、序盤→中盤→終盤で緊張→高揚→余韻の流れを作る）を踏まえて
  **9曲から各役割1曲ずつ計3曲**に直接絞り込む（2026-08-04〜: `/consult`経由の
  Gemini対話+Opus統合をやめ、Claudeが直接判断する方式に変更。BGM選定はタグ・制約への
  照合作業であり境界が明確なため、`/consult`本来の用途であるオープンな戦略相談ほどの
  重さは不要と判断。判断材料はテキストのみ（曲の特徴・タグ・使用履歴）であり、
  実音声は聴いていないことに留意する — 実音声ベースの検証は次の`sc_bgm_final_check.py`で行う）。
- **選定3曲が確定したら、選ばれなかった曲を `~/Desktop/SC/BGM/` から削除して3曲のみ残し、
  `sc_bgm_final_check.py --episode ep{NNN}` を実行する（2026-08-01〜）。**
  このスクリプトは選定3曲の実音声と STEP 3A で生成済みの `ep{NNN}_制作確認書.txt` 全文を
  Gemini のマルチモーダル音声理解に渡し、「重厚なオーケストラ調」方針への適合・各曲のトーンと
  対応シーン群の内容との一致・3曲を通した緊張→高揚→余韻の流れの破綻有無・音質面の懸念を
  実音声ベースで最終検証する（`/consult` のテキストのみの判断を補完するステップ）。
  判定結果（各曲評価＋総合GO/差し替え推奨）は保持しておき、STEP5C後の統合確認メッセージに含める。
- `~/Desktop/SC/BGM/` に選定3曲を残したまま次に進む。**ユーザーへの提示・試聴確認は
  STEP5C後の統合確認まで行わない**（2026-08-04〜。`open`コマンドでのFinder自動オープンや
  `~/Desktop/SC/` 直下へのコピーもここでは行わない）。
- 差し替え希望が出た場合（統合確認時）は該当役割のみ再選定し、再度
  `sc_bgm_final_check.py` を実行してから改めて確認を求める。

### 完了報告

制作確認書のファクトチェック・QA結果を画面に表示する（情報提供・常に表示）。
**サムネイル・BGMの確認はここでは求めない**（STEP5C後の統合確認にまとめる。2026-08-04〜）。

**⚠️ 重要: TTS・画像生成（STEP 5A/5B）は、ナレーションに⚠️がある場合はユーザーの承認が
取れるまで絶対に開始しない。** ⚠️が無い場合はこの報告は情報提供のみで、確認を待たず
そのままSTEP 5A/5Bへ進む。承認前にTTSを走らせると、ナレーション修正が必要になった際に
再生成が必要になるため、⚠️があるケースだけは例外的に早期ゲートを残す。

**画像プロンプトQAの⚠️は確認なしに即座に自動修正する（2026-08-04〜）。** ナレーションの
⚠️（ファクトチェック・英語QA）とは扱いを分ける。理由: 画像プロンプトの修正はTTS/画像生成の
「前」に行う変更であり、間違っていても後段のSTEP 5C（画像QA・自動2回リトライ＋Claude一次判断）
でもう一段検出される安全網がある。ナレーション内容のような主観的判断（表現の適否）を伴わない
機械的・構造的な指摘（写実指定句の欠落、他カットとの構図重複など）が大半のため、ユーザー確認を
挟む必要性が薄い。`episodes/ep{NNN}.json` の該当箇所を直接編集し、「対応済み」として報告する
（「対応してよいか」とは聞かない）。

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 ファクトチェック・QA 結果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌自動修正済み（{N}件）:
  🔧 S05: "1582年" → "1600年" に修正（ep.json 更新済み）
  🔧 S03: "Toyotomi dynasty" → "Toyotomi clan" に修正済み

🖼️ 画像プロンプトQA・自動対応済み（{N}件）:
  🔧 S02/S05/S06...: 写実指定句を追記
  🔧 S01: サムネイルとの構図重複を解消

⚠️ 要確認（{N}件、ナレーションのみ）:
  ⚠️ S07: "Japan's most powerful" → 最上級の多用（S02・S11 と重複）

✅ 年号・日付: 全件確認済み
✅ 文法・スペル: 問題なし
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

❌自動修正済み・🖼️画像プロンプト対応済み・⚠️なし → 「✅ QA完了 — 問題なし」を表示し、
確認を待たずそのまま STEP 5A/5B へ進む。
⚠️（ナレーション）がある場合のみ、内容を表示してユーザーに確認を求める（下記ループ）。

---

### 確認・修正ループ（ナレーション⚠️がある場合のみ）

- **ナレーション修正あり（❌ / ⚠️）** → `episodes/ep{NNN}.json` の該当シーンを直接編集して修正。`~/Desktop/SC/ep{NNN}_制作確認書.txt` も上書き更新。修正箇所を報告して再確認を求める。
- **OK** → STEP 5A/5B へ進む

画像プロンプトQAの⚠️はこのループの対象外（完了報告の時点で既に対応済みのため）。
サムネイル・BGMの見直しはここでは扱わない（STEP5C後の統合確認で扱う）。

---

## STEP 4 — Google Driveへ移動

**⚠️ 実行タイミング（2026-08-04〜変更）: このSTEPはSTEP3完了直後ではなく、
STEP 5C（画像QA）後の統合確認でユーザーのOKが出てから実行する。** 以前はSTEP3の
サムネイル・BGM確認が取れた時点で実行していたが、確認ポイントを1箇所に統合したため、
BGMの`bgm_library.json`本登録が「まだ承認されていないBGM」に対して発生することを防ぐ目的で
このタイミングに変更した。ドキュメント内の記載順序はSTEP3の直後のままだが、
**実際の実行順序は STEP1→2A→2B→3A/3B/3C→5A/5B→5C→統合確認→(このSTEP4)→5D→6**。

すべてOKが取れたら、デスクトップのファイルをGoogle Driveエピソードフォルダへ移動する：

```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}"
mkdir -p "$DRIVE/audio" "$DRIVE/images" "$DRIVE/images_shorts"

# 制作確認書を移動
mv "$HOME/Desktop/SC/ep{NNN}_制作確認書.txt" "$DRIVE/"

# サムネイルを移動
mv "$HOME/Desktop/SC/ep{NNN}_thumbnail.png" "$DRIVE/"

# シーン画像・画像QA結果を移動（sc_image_gen.py の出力）
mv "$HOME/Desktop/SC/ep{NNN}/images/"*.png "$DRIVE/images/" 2>/dev/null
mv "$HOME/Desktop/SC/ep{NNN}/images_shorts/"*.png "$DRIVE/images_shorts/" 2>/dev/null
mv "$HOME/Desktop/SC/ep{NNN}/image_qa_result.json" "$DRIVE/" 2>/dev/null
mv "$HOME/Desktop/SC/ep{NNN}/image_qa_result_shorts.json" "$DRIVE/" 2>/dev/null
mv "$HOME/Desktop/SC/ep{NNN}/image_qa_result_face.json" "$DRIVE/" 2>/dev/null

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
```

**⚠️ 2026-08-24〜変更: `~/Desktop/SC/` フォルダはこの時点では削除しない。**
以前はここで `rm -rf "$HOME/Desktop/SC"` していたが、ユーザーが動画完成後もDesktopフォルダ上で
BGM・サムネイル・完成動画をまとめて確認したいとの要望により、削除タイミングをSTEP 6完了後・
ユーザーの最終OK後まで遅らせるように変更した。STEP 4完了時点ではDriveへの登録（画像・BGM）のみ
行い、Desktopの残骸（BGM候補ファイル・サムネイル・制作確認書の元ファイル等）はそのまま残す。

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

**保存先（2026-08-23〜）:** `sc_image_gen.py` の出力は `~/Desktop/SC/ep{NNN}/images/`・
`~/Desktop/SC/ep{NNN}/images_shorts/` に保存される（確認用。制作確認書・サムネイル・BGMと
同じ運用）。**Google Drive への保存はこの時点では行わない。** STEP5C統合確認でOKが出てから
STEP4でDriveへ移動する。

---

## STEP 5C — 画像QA、およびサムネイル・BGM・シーン画像の統合確認
（2026-07-28〜: 目視確認を追加。2026-08-04〜: サムネイル・BGM確認をここに統合）

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
- QAの自動チェック（`all_ok`）が通っても、それだけでは STEP 4・5D・6 には進まない。
  下記の「統合確認」で、サムネイル・BGMとまとめてユーザーが実際に画像を見て確認した上で
  OKを得る（2026-07-28〜、2026-08-04〜サムネイル・BGMと統合）。

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

`~/Desktop/SC/ep{NNN}/` の以下のファイルを読み込む（2026-08-23〜、STEP4完了前なので
まだGoogle Driveではなくデスクトップの確認用フォルダにある）：
```bash
cat ~/Desktop/SC/ep{NNN}/image_qa_result.json
cat ~/Desktop/SC/ep{NNN}/image_qa_result_shorts.json
# --face を使用した場合のみ:
cat ~/Desktop/SC/ep{NNN}/image_qa_result_face.json
```

各JSONの `all_ok` を確認する：
- `all_ok: true` → 問題なし
- `all_ok: false` → `warnings` 配列に `{scene_id, issues}` が入っている（＝2回試行済みで解決しなかったシーン）

### WARNINGへの一次対応（Claude判断、2026-08-02〜）

`warnings` に残ったシーンは、ユーザーに見せる前に**まずClaudeが判断・対応する**
（自動2回リトライは機械的な修正なので、次はClaudeが実際に画像とissueを見て判断する）。
各WARNINGシーンについて、Read ツールで実際の画像を直接見て、issueの内容と照らし合わせる：

1. **許容できると判断した場合** → そのシーンは解決済み扱いとし、ユーザーには諮らない
   （後述の統合確認で他の画像と同様に見てもらう機会はある）。
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
   - 不合格 → このシーンのみ後述の「統合確認」でユーザーに諮る

この一次対応の結果は後述の「統合確認」にまとめて示す（次項の内部レポート参照）。
ナレーション本文や他のJSONフィールドの修正は絶対に行わない（＝TTS再生成は発生させない）。

### 内部レポート（ユーザーには出さない、次の統合確認の材料にする）

`all_ok: true`（全ファイル、またはClaudeの一次対応で全件解決）か、
未解決のWARNINGが残るかを把握しておく：

```
自動2回リトライ後のWARNING: {N}件
→ Claude判断で許容: {N}件 / Claude修正で解決: {N}件
→ 未解決のまま: {N}件
[未解決] S{N}: {issues の内容}
```

### シーン確認ページの生成（2026-08-28〜）

統合確認メッセージを組み立てる前に、画像・ナレーション音声・BGM・日本語訳を1ページで
突き合わせ確認できるHTMLページを生成する（`sc_scene_review.py`。この時点ではまだ
STEP4未実行のため、画像・BGM候補ともDesktop/SC側から読み込まれる）：

```bash
python3 sc_scene_review.py --episode ep{NNN}
```

出力: `~/Desktop/SC/ep{NNN}_review.html`（ブラウザで開いて確認する用。Finderの自動オープンは
行わない）。生成後は下記の統合確認メッセージにこのページのパスを含める。

**⚠️ 画像はHTMLにbase64で直接埋め込まれるため、生成後に元画像（`images/`・`images_shorts/`）
を再生成しても自動反映されない（ep090で実際に発生: 修正済みのはずのシーンをレビューページ上で
見たユーザーが「直っていない」と指摘 → 原因はページの再生成漏れだった）。統合確認・確認修正
ループの中でシーン画像を1枚でも再生成した場合は、ユーザーに再確認を求める前に必ず
`sc_scene_review.py` を再実行してページを最新化すること。**

### 統合確認 — サムネイル・BGM・シーン画像をまとめて確認（2026-08-04〜）

STEP3で準備済みのサムネイル・BGMと、ここまでの画像QA結果を**1回のメッセージ**で
まとめてユーザーに提示する（旧: STEP3後にサムネイル・BGM、STEP5C後に画像QAアクション、
STEP5C後に目視確認、と最大3回に分かれていた確認をここに統合）。
ナレーションに⚠️があった場合はSTEP3完了報告の時点で既に解決済みなので、ここでは扱わない。

**⚠️ 表示方法の制約（検証済み）:** 1ターンに画像を配信するツール呼び出し
（`Read` や `SendUserFile`）が複数あると、ユーザー側に表示されない。
Read単体1回のみ・他の画像配信呼び出しなしのターンでのみ表示に成功することを確認済み。
したがって：
- サムネイルは Read ツールで**1回だけ**表示する
- シーン画像・BGMはファイル自体を送らず、`~/Desktop/SC/ep{NNN}/images/`／`~/Desktop/SC/BGM/`
  のフォルダパスを案内する方式にする（全シーンを一括でReadツールに貼り付ける、または
  `SendUserFile` でまとめて送る、という方法は**行わない**）
- 上記の案内テキストと、サムネイルのRead表示は**同じターンでよい**（禁止されているのは
  画像"配信"ツールの複数回呼び出しであり、テキスト＋Read1回の組み合わせは問題ない）

**提示するメッセージ（画像QAに未解決WARNINGが無い場合）:**
```
制作素材が揃いました。まとめてご確認ください。

📷 サムネイル: 下に表示します
🎵 BGM: ~/Desktop/SC/BGM/ に3曲（intro/main/outro）を用意しました。
   試聴してご確認ください（sc_bgm_final_check.py判定: {総合GO/差し替え推奨}）
🖼️ シーン画像: ~/Desktop/SC/ep{NNN}/images/ フォルダでご確認ください
   （画像QA: 全{total}シーン問題なし）
🎬 シーン確認ページ: ~/Desktop/SC/ep{NNN}_review.html をブラウザで開くと、
   画像・ナレーション音声・BGM・日本語訳をシーンごとに突き合わせて確認できます

すべて問題なければお知らせください。
```
（このテキストと同じターンで、Read ツールでサムネイル画像を1回だけ表示する）

**画像QAに未解決WARNINGが残っている場合、上記の🖼️部分を以下に差し替える：**
```
🖼️ シーン画像: ~/Desktop/SC/ep{NNN}/images/ フォルダでご確認ください。
   このうち以下は自動修正・Claudeでの修正を試みましたが解決しませんでした。
   特に注意してご覧いただき、そのまま許容するか差し替えを希望するかお知らせください。
     S{N}: {issues の内容}
     ...
```

**確認・修正ループ:**
- **サムネイルを見直したい** → 再生成して再度表示する
- **BGMを見直したい** → 該当役割のみ再選定し、`sc_bgm_final_check.py` を再実行してから
  再度確認を求める
- **シーン画像を見直したい** → 該当シーンの `image_prompt` を修正して
  `sc_image_gen.py --episode ep{NNN} --scenes N`（Shortsなら `--shorts --scenes N` も追加）で
  再生成し、再度そのシーン（1枚のみ）を表示して確認を取る
- **すべてOK** → STEP 4（Google Driveへ移動・BGM本登録）→ STEP 5D の順に進む

ナレーション変更の選択肢は絶対に提示しない（STEP3で確定済み）。
OKが出るまで STEP 4 には進まない。

---

## STEP 5D — シーン画像解析・zoom_anchor 書き込み

STEP 5C（画像QA・統合確認・再生成含む）とSTEP 4（Google Driveへ移動・BGM本登録）が
完了し、最終的な画像が確定した後に実施する。

**2026-08-04〜: Gemini Visionに委任する方式に変更。** 以前はClaude自身がReadツールで
対象シーン画像（最大20枚/話）を直接読み込んで判定していたが、これがメイン会話の
コンテキストとClaude利用枠（5時間制限）を大きく圧迫していたため（SC・LWを並行制作すると
1時間程度で制限に達する一因と判明）、`sc_image_gen.py`の画像QAと同じ考え方で
`gemini-3.6-flash`への委任に変更した。Gemini側の追加コストはflashティアの単純な
Visionタスクのため無視できる水準。

```bash
python3 sc_zoom_anchor.py --episode ep{NNN}
```

対象シーン（`character_ref`が設定され、かつ2人構図でない — image_promptに
"on the left"/"on the right" 系キーワードが両方は含まれない）シーンについて、
各シーン画像をGeminiに渡し、主被写体の「顔〜胸」あたりの重心を正規化座標
（x: 0.0=左端〜1.0=右端、y: 0.0=上端〜1.0=下端）で判定させ、
`episodes/ep{NNN}.json` の該当シーンに直接書き込む（スクリプト内で完結）。
それ以外のシーンはスキップされ、zoom_anchor は null のまま。

**⚠️ 判定精度の確認（当面の注意）:** Gemini移行直後のためClaude目視判定との
座標の傾向差（特にy軸）がまだ十分検証できていない。**この変更後1〜2話は、
`sc_video_gen.py`で生成した動画のズーム構図（顔が変に切れていないか等）を
特に注意して確認すること。** 目立ったズレがあれば `--scenes N` で該当シーンのみ
再判定するか、`episodes/ep{NNN}.json` の `zoom_anchor` を手動で微調整してよい。

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

出力は Google Drive の `ep{NNN}/output/` に生成される。完了後、ユーザーが Desktop 上で
サムネイル・BGM・完成動画をまとめて確認できるよう、Drive の出力を `~/Desktop/SC/` へコピーする
（2026-08-24〜。move ではなく copy — Drive 側が正本のまま）：

```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}/output"
cp "$DRIVE/Samurai Chronicles ep{NNN}.mp4" "$HOME/Desktop/SC/"
cp "$DRIVE/ep{NNN}_shorts.mp4" "$HOME/Desktop/SC/"
cp "$DRIVE/ep{NNN}.srt" "$HOME/Desktop/SC/"
```

完了後：
```
ep{NNN} の制作が完了しました。

出力ファイル（~/Desktop/SC/ に確認用コピーを用意しました）:
  - Samurai Chronicles ep{NNN}.mp4
  - ep{NNN}_shorts.mp4
  - ep{NNN}.srt

動画を確認してください。問題があればお知らせください。確認できたら /sc-upload でアップロードしてください。
```

**⚠️ 重要:** STEP 6 完了後はここで必ず停止する。
`sc_sns_up.py` の自動実行・`/sc-upload` の自動呼び出しは絶対に行わない。
アップロードはユーザーが明示的に `/sc-upload` を実行した時のみ行う。

**Desktopフォルダの削除（2026-08-25〜変更）:** ここでは個別の「OK」待ちを行わない。
`/sc-upload` の起動自体が「動画を確認し問題なしと判断した」という意思表示とみなすため、
`rm -rf "$HOME/Desktop/SC"` によるDesktop作業フォルダの削除は `/sc-upload` 側
（STEP 1）で行う（詳細は `sc-upload.md` 参照）。Drive側にはSTEP4・STEP6でそれぞれ
登録・コピー済みのため、削除しても実データは失われない。ユーザーが動画に問題を指摘した
場合は、該当箇所を修正してSTEP6を再実行し、Desktopへの再コピー→再確認のループを
繰り返す（`/sc-upload` が実行されるまでDesktopフォルダは自然に残り続ける）。
