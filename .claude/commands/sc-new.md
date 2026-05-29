# /sc-new — Samurai Chronicles 新エピソード生成

topics_queue.json から次のトピックを選び、動画生成まで一気に進めるコマンド。

## 定数

- エピソードJSON: `$HOME/samurai-chronicles/episodes/`
- トピックキュー: `$HOME/samurai-chronicles/topics_queue.json`
- Google Drive: `~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/`

---

## STEP 1 — 次のトピックを確認する

`topics_queue.json` を読み込み、`status: "pending"` の件数を確認する。

### 残り5件以下の場合 — トピック補充

新しいトピックを5件提案し、ユーザーに確認してもらう。

提案フォーマット：
```
残りトピックが少なくなりました。新しい候補を5件提案します：

1. ep031「...」（era / Priority A）
   ※ メモ
2. ep032「...」
...

追加しますか？（はい / 修正あり / 不要）
```

OKが取れたら `topics_queue.json` の `queue` に追記し、`total_topics` と `last_updated` を更新する。

---

`status: "pending"` のうち**配列の先頭（最初に現れるもの）**を1件提案する。（episode_id の番号順ではなく、配列の並び順で決まる）

表示フォーマット：
```
次のエピソード候補：

ep002「The Honnoji Incident」（Sengoku / Priority A）
※ ep001 アウトロでティーザー済み

これにしますか？（はい / 別のトピックを指定）
```

---

## STEP 2 — エピソード内容を生成する

選ばれたトピックをもとに、以下を含む完全なエピソードJSONを生成する。

**JSONの内容は画面に出力しない。** 生成後すぐにファイルへ保存する。

### 生成ルール

**YouTube タイトルの型（CTR最大化）:**

海外歴史チャンネルで再生数が取れるタイトルには共通の型がある。必ずいずれかの型に当てはめること。

- 型A: `"The [Adjective] [Person] Who [Did Something Shocking]"`
- 型B: `"Why [Famous Person] Really [Did Something]"`
- 型C: `"The Real Reason [Famous Event] Happened"`
- 型D: `"The [Event] That Changed Japan Forever"`

× 避ける: `"The History of Miyamoto Musashi"`（説明的すぎる）
○ 良い: 裏切り・転落・奇跡・復讐など「人間ドラマ」としてフックを作る

シリーズ構成の場合はタイトル末尾に統一表記する:
```
例: "The Betrayal at Honnoji | Sengoku's Most Brutal Betrayals #1"
```

---

**ナレーション（各シーン）:**
- BBC/Netflix歴史ドキュメンタリー調の英語
- 1シーン約80〜100語（約15〜18秒の読み上げ尺）
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

**shorts_highlight_scene:**
- クライマックス**直前**のシーンを選ぶ（緊張が最高潮に達した瞬間）
- 「この後どうなる？」と思わせる引きを作り、本編への誘導フックにする
- climax シーンそのものではなく、その1〜2シーン前が理想

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

## STEP 3 — JSONを保存し、topics_queue.json を更新する

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

## STEP 4 — 制作確認書・サムネイル・BGMを並行して準備する

制作確認書の生成・サムネイル画像生成・BGMダウンロードを**同時に**バックグラウンドで実行する。

### 制作確認書（Claudeが直接生成）

**制作確認書の内容は画面に一切出力しない。** バックグラウンドで以下を実行してデスクトップに保存する：

1. エピソードJSONの全シーンを日本語に翻訳する
2. 全ナレーションのファクトチェックを行う
3. 以下のフォーマットで `ep{NNN}_制作確認書.txt` を組み立ててデスクトップに保存する

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

▼ YouTube 説明文（英語）
{youtube_description}

▼ タグ
{youtube_tags をカンマ区切り}

================================================================
【各シーンのナレーション】
================================================================

▶ S{id:02d}  [{type}]  キャラクター: {character_ref or —}  想定尺: {duration_seconds}秒

  【EN】
  {narration}

  【JA】
  {日本語訳}

----------------------------------------
... （全シーン繰り返し）

================================================================
【ファクトチェック結果】
================================================================

【✅ 確認済み・正確な情報】
...

【⚠️ 注意・議論あり】
...

【❌ 誤り・修正が必要】
...

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
【確認・承認】
----------------------------------------
□ 内容確認完了
□ ファクトチェック問題なし
□ 英語QA・画像プロンプトQA問題なし
□ BGM選択完了
□ 動画生成GO

備考:

================================================================
```

**Google Drive への保存はこの時点では行わない。**

---

### サムネイル画像（Claudeが直接生成）

エピソードJSONの `thumbnail_prompt` にテキストオーバーレイ指示を加えてGeminiで生成し、デスクトップに保存する。

**テキストオーバーレイ指示（プロンプトに追記）:**
```
Bold text overlay at the top in large white block letters with dark drop shadow: "{EPISODE_TITLE_SHORT}".
Smaller text at the bottom in white: "{SUBTITLE}".
Text must be clearly legible, sharp, and properly spelled.
Modern cinematic concept art style, dramatic lighting, film production illustration quality. 16:9 aspect ratio, 1280x720.
```

- `EPISODE_TITLE_SHORT`: エピソードタイトルを短く大文字で（例: "THE HONNOJI INCIDENT"）
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
# 保存先: ~/Desktop/ep{NNN}_thumbnail.png
```

**Google Drive への保存はこの時点では行わない。**

---

### BGM（Freesound 2曲 + ライブラリ 2曲 = 計4曲）

Freesound から2曲ダウンロードし、`bgm_library.json` からエピソードの雰囲気に合う2曲を選んでデスクトップにコピー。計4曲からユーザーが選ぶ。

#### ① Freesound から2曲ダウンロード

エピソードのムード（タイトル・シーン構成・感情トーン）から2〜3語の英語クエリを2本生成し、ダウンロードする。

**クエリ生成ルール:**
- 必ず短く（2〜3語）
- **必ず `orchestral` または `epic` または `cinematic` のいずれかを含める**
- トーン修飾語（組み合わせて使う）: dramatic, heroic, dark, powerful, epic, tense, triumphant
- 楽器補強（単体では使わない）: strings, brass, choir, taiko, percussion
- 良い例: `"epic orchestral"` / `"dramatic cinematic strings"` / `"dark orchestral taiko"` / `"heroic brass orchestra"`
- **禁止キーワード:** shamisen 単体, piano 単体, ambient, meditation, acoustic, folk, traditional, nature, forest, rain, calm, relaxing, light

```bash
mkdir -p "$HOME/Desktop/BGM"
FREESOUND_API_KEY=$FREESOUND_API_KEY python3 $HOME/lamp-whisper/freesound_download.py \
  "<Q1>" "<Q2>" \
  "$HOME/Desktop/BGM/" \
  --round 0
```

**部分失敗時（一部スロットが0件・404）:** 失敗したスロットのみ `--start-slot <N>` で別クエリに差し替えて補完する。ダウンロード完了後、`.credit.txt` を退避：

```bash
mkdir -p /tmp/sc_bgm_credits
mv "$HOME/Desktop/BGM/BGM_candidate_"*.credit.txt /tmp/sc_bgm_credits/ 2>/dev/null || true
```

#### ② ライブラリから2曲選択

`bgm_library.json` を読み込み、エピソードのタイトル・ナレーション・シーン構成（climax/rising_action の多さ、トーン）を考慮してタグが合致する上位2件を選ぶ。

選んだ2件を `~/Desktop/BGM/` にコピー（試聴用の一時コピー。選択後は削除）：

```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles"
cp "$DRIVE/<path1>" "$HOME/Desktop/BGM/BGM_library_01_<name>.mp3"
cp "$DRIVE/<path2>" "$HOME/Desktop/BGM/BGM_library_02_<name>.mp3"
# CC BY の場合は credit.txt も /tmp/sc_bgm_credits/ に保存しておく
```

`~/Desktop/BGM/` に合計4曲が並ぶ：
```
BGM_candidate_01_xxx.mp3   ← Freesound 新規
BGM_candidate_02_xxx.mp3   ← Freesound 新規
BGM_library_01_xxx.mp3     ← ライブラリ
BGM_library_02_xxx.mp3     ← ライブラリ
```

---

### 完了報告

3つすべてが完了したら、制作確認書で見つかった問題点を**画面に表示**してユーザーに確認を取る。

**⚠️ 重要: TTS・画像生成（STEP 5）はユーザーの承認が取れるまで絶対に開始しない。**
ナレーション修正が必要な問題がある場合、承認前にTTSを走らせると再生成が必要になる。

```
制作確認書・サムネイル・BGM候補の準備ができました。

📄 ep{NNN}_制作確認書.txt — デスクトップに保存済み
🖼️ ep{NNN}_thumbnail.png — デスクトップに保存済み
🎵 BGM候補 4曲 — デスクトップに保存済み
  1. {ファイル名}（{尺}s）[{ライセンス}]
  2. {ファイル名}（{尺}s）[{ライセンス}]
  3. {ファイル名}（{尺}s）[{ライセンス}]
  4. {ファイル名}（{尺}s）[{ライセンス}]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 ファクトチェック・QA 結果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
（制作確認書のファクトチェック・英語QA・画像プロンプトQAで
 見つかった問題をここに列挙。問題なければ「✅ 問題なし」と1行）

例:
  ❌ S03: "Toyotomi dynasty" → "Toyotomi clan" に修正が必要
  ⚠️ S07: "Japan's most powerful" → 最上級の多用（S02・S11 と重複）
  ✅ 文法・スペル: 問題なし
  ✅ 画像プロンプト: 問題なし
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

サムネイルを確認し、BGMは1曲だけ残して削除してください。
❌ の修正が必要な場合はここで指示してください。
すべてOKなら「OK」と教えてください。
```

---

### 確認・修正ループ

ユーザーの回答に応じて対応する：

- **ナレーション修正あり（❌ / ⚠️）** → `episodes/ep{NNN}.json` の該当シーンを直接編集して修正。デスクトップの制作確認書も上書き更新。修正箇所を報告して再確認を求める。
- **サムネイルをやり直したい** → デスクトップの `ep{NNN}_thumbnail.png` を削除して再生成。
- **BGMをやり直したい** → デスクトップの4曲と `/tmp/sc_bgm_credits/` 内の credit.txt を削除し、`--round` を1増やして再ダウンロード＋ライブラリ再選択。
- **すべてOK** → STEP 4b へ進む

---

## STEP 4b — Google Driveへ移動

すべてOKが取れたら、デスクトップのファイルをGoogle Driveエピソードフォルダへ移動する：

```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}"
mkdir -p "$DRIVE/audio"

# 制作確認書を移動
mv "$HOME/Desktop/ep{NNN}_制作確認書.txt" "$DRIVE/"

# サムネイルを移動
mv "$HOME/Desktop/ep{NNN}_thumbnail.png" "$DRIVE/"

# 残ったBGM1曲を判定: Freesound新規 or ライブラリ
CHOSEN=$(ls "$HOME/Desktop/BGM/BGM_candidate_"*.mp3 "$HOME/Desktop/BGM/BGM_library_"*.mp3 2>/dev/null | head -1)
CHOSEN_STEM=$(basename "$CHOSEN" .mp3)

if [[ "$CHOSEN" == *"BGM_candidate_"* ]]; then
  # Freesound新規: エピソードフォルダに移動
  mv "$CHOSEN" "$DRIVE/audio/ep{NNN}-BGM.mp3"
  # bgm_library.json に新規エントリを追加
  python3 $HOME/samurai-chronicles/sc_bgm_library.py \
    --add --episode ep{NNN} --file "$DRIVE/audio/ep{NNN}-BGM.mp3" \
    --stem "$CHOSEN_STEM"
  # クレジット注入（CC BY の場合）
  CREDIT="/tmp/sc_bgm_credits/${CHOSEN_STEM}.credit.txt"
  if [ -f "$CREDIT" ]; then
    python3 $HOME/samurai-chronicles/sc_inject_bgm_credit.py \
      --episode ep{NNN} --credit-file "$CREDIT"
  fi
else
  # ライブラリ既存曲: episode JSON に bgm_source を記録、ファイルは移動しない
  python3 $HOME/samurai-chronicles/sc_bgm_library.py \
    --use-library --episode ep{NNN} --stem "$CHOSEN_STEM"
  # ライブラリ曲の試聴コピーを削除
  rm -f "$CHOSEN"
  rmdir "$HOME/Desktop/BGM" 2>/dev/null || true
  # クレジット注入（CC BY の場合）
  CREDIT="/tmp/sc_bgm_credits/${CHOSEN_STEM}.credit.txt"
  if [ -f "$CREDIT" ]; then
    python3 $HOME/samurai-chronicles/sc_inject_bgm_credit.py \
      --episode ep{NNN} --credit-file "$CREDIT"
  fi
fi

# /tmp の残 credit.txt をすべて削除
rm -f /tmp/sc_bgm_credits/BGM_candidate_*.credit.txt
```

credit.txt が存在した場合（CC BY）は、制作確認書の BGM 欄を更新する：
- BGM タイトル・作者名
- Freesound URL（`https://freesound.org/s/{SOUND_ID}/`）
- ライセンス（CC BY 4.0）
- 概要欄に貼るクレジットテキスト（`🎵 Music: ... by ... (freesound.org) — CC BY 4.0`）

BGM が CC0 の場合は「CC0 — クレジット不要」と記載。

**更新後の BGM 欄フォーマット（CC BY の場合）:**
```
BGM           : ✅ {タイトル} by {作者名}
  Freesound URL : https://freesound.org/s/{SOUND_ID}/
  ライセンス    : CC BY 4.0
  概要欄クレジット: 🎵 Music: {タイトル} by {作者名} (freesound.org) — CC BY 4.0
```

**更新後の BGM 欄フォーマット（CC0 の場合）:**
```
BGM           : ✅ {タイトル} by {作者名}
  Freesound URL : https://freesound.org/s/{SOUND_ID}/
  ライセンス    : CC0（クレジット不要）
```

Freesound の SOUND_ID は BGM ファイル名（`BGM_candidate_XX_{SOUND_ID}_...mp3`）から取得する。

移動完了を報告する。

---

## STEP 5 — 素材を自動生成する

以下を実行する：

```bash
python3 sc_tts_gen.py --episode ep{NNN}                    # ナレーション音声生成（本編用・シーンタイプ別感情トーン）
python3 sc_tts_gen.py --episode ep{NNN} --teaser           # トレイラーイントロTTS生成（S00_teaser.wav）
python3 sc_tts_gen.py --episode ep{NNN} --shorts           # Shorts専用TTS生成（S00_shorts.wav）
python3 sc_image_gen.py --episode ep{NNN}                  # 本編用画像生成（16:9）
python3 sc_image_gen.py --episode ep{NNN} --shorts         # Shorts用画像生成（9:16）
```

---

## STEP 5b — シーン画像解析・zoom_anchor 書き込み

画像生成完了後、Claude が各シーン画像を直接 Read ツールで読み込み、ズーム焦点座標を判定して
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

## STEP 5c — 画像 × ナレーション 整合性チェック

STEP 5b 完了後、動画生成の**前**に実施する。

### ⚠️ 絶対ルール：ナレーション変更は提案しない

このステップで修正できる手段は**画像の再生成のみ**。
ナレーション・JSONの修正は一切提案しない（＝TTS再生成は絶対に発生させない）。
ナレーションの品質はSTEP 4で保証済みとみなす。
「ナレーションに問題がある」と感じても、画像側で対応するか [B] 許容で進む。

### チェック内容

Google Drive の `images/S01.png`〜`S{N}.png` を Read ツールで読み込み、
各シーン画像を image_prompt と照合する。

確認する観点（すべて「画像の問題」として扱う）:
- 画像が image_prompt の指示と大きく乖離している（被写体・構図・時代設定）
- AI 特有の不自然さで目立つもの（崩れた文字、異様な手・顔）
- 冒頭と終盤で同じキャラクターの同じ構図が被っていないか（reveal 演出の破綻）

**問題ありのシーンのみ報告**（正常シーンは省略）。
画像が多い場合は S01・hook・キャラクター初登場・クライマックス・S19 を優先。

### レポート出力フォーマット

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  画像 QA — ep{NNN}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [WARNING] S{N}: {問題の説明} → 画像再生成を推奨
  ✅ 主要シーン: 問題なし
  WARNING {N}件
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

問題がなければ「✅ 画像 QA: 全シーン問題なし → STEP 6 へ進みます」と1行で報告して即座に次へ。

### アクション

WARNING がある場合のみユーザーに確認：
```
{N}件の画像に問題が見つかりました。
[A] 画像を再生成して修正（zoom_anchor も再判定）
[B] 許容してそのまま動画生成へ進む
```

ナレーション変更の選択肢は絶対に提示しない。

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
