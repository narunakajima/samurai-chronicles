# /sc-new — Samurai Chronicles 新エピソード生成

topics_queue.json から次のトピックを選び、動画生成まで一気に進めるコマンド。

## 定数

- エピソードJSON: `/Users/claude/samurai-chronicles/episodes/`
- トピックキュー: `/Users/claude/samurai-chronicles/topics_queue.json`
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

`status: "pending"` のうち最も若い `episode_id` を1件提案する。

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

### 生成ルール

**ナレーション（各シーン）:**
- BBC/Netflix歴史ドキュメンタリー調の英語
- 1シーン約150〜200語
- 各シーンで次シーンへの引きを作る
- hook → setup → rising_action → climax → falling_action → insight → teaser → outro の構成

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
- 最も劇的・視覚的に強いシーンのID（クライマックス付近）

### JSONフォーマット

```json
{
  "episode_id": "ep{NNN}",
  "episode_title": "...",
  "youtube_title": "...",
  "youtube_description": "...",
  "youtube_tags": [...],
  "total_scenes": 20,
  "shorts_highlight_scene": N,
  "thumbnail_prompt": "...",
  "scenes": [
    {
      "scene_id": 1,
      "type": "hook",
      "duration_seconds": 20,
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

📚 References:
1. {参考文献1}
2. {参考文献2}
3. {参考文献3}

#{tag1} #{tag2} ...
```

**禁止:** 「AI」「AI-generated」などAI関連の文言は一切含めない。

---

## STEP 3 — JSONを保存し、topics_queue.json を更新する

```bash
# episodes/ に保存
/Users/claude/samurai-chronicles/episodes/ep{NNN}.json
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

## STEP 4 — 制作確認書とBGMを並行して準備する

制作確認書の生成とBGMダウンロードを**同時に**バックグラウンドで実行する。

### 制作確認書（Claudeが直接生成）

画面に内容を表示せず、バックグラウンドで以下を実行してデスクトップに保存する：

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
【確認・承認】
----------------------------------------
□ 内容確認完了
□ ファクトチェック問題なし
□ BGM選択完了
□ 動画生成GO

備考:

================================================================
```

**Google Drive への保存はこの時点では行わない。**

---

### BGM（Freesoundから3曲）

エピソードのムード（タイトル・シーン構成・感情トーン）から2〜3語の英語クエリを3本生成し、ダウンロードする。

**クエリ生成ルール:**
- 必ず短く（2〜3語）
- 楽器・音楽系キーワードに絞る（orchestral, strings, taiko, shamisen, cinematic, epicなど）
- 環境音系（forest, rain, nature, ambience など）は禁止

```bash
FREESOUND_API_KEY=$FREESOUND_API_KEY python3 /Users/claude/.claude/scripts/freesound_download.py \
  "<Q1>" "<Q2>" "<Q3>" \
  "$HOME/Desktop/" \
  --round 0
```

**部分失敗時（一部スロットが0件・404）:** 失敗したスロットのみ `--start-slot <N>` で別クエリに差し替えて補完する。全スロット再実行は禁止。ダウンロード完了時点でデスクトップに必ず3曲揃っていること。

**CC BY の曲が含まれる場合:** ダウンロード完了時に帰属クレジットをメモしておく。

---

### 完了報告

制作確認書・BGMの両方が完了したら、ユーザーに報告する：

```
制作確認書とBGM候補の準備ができました。

📄 ep{NNN}_制作確認書.txt — デスクトップに保存済み
🎵 BGM候補 3曲 — デスクトップに保存済み
  1. {ファイル名}（{尺}s）[{ライセンス}]
  2. {ファイル名}（{尺}s）[{ライセンス}]
  3. {ファイル名}（{尺}s）[{ライセンス}]

確認書を読んで、BGMは1曲だけ残して2曲削除してください。
両方OKなら教えてください。修正があればお知らせください。
```

---

### 確認・修正ループ

ユーザーの回答に応じて対応する：

- **確認書に修正あり** → 該当箇所を修正してデスクトップのファイルを上書き保存。再確認を求める。
- **BGMをやり直したい** → デスクトップの候補3曲を削除し、`--round` を1増やして再ダウンロード。
- **両方OK** → STEP 4b へ進む

---

## STEP 4b — Google Driveへ移動

両方OKが取れたら、デスクトップのファイルをGoogle Driveエピソードフォルダへ移動する：

```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}"
mkdir -p "$DRIVE/audio"

# 制作確認書を移動
mv "$HOME/Desktop/ep{NNN}_制作確認書.txt" "$DRIVE/"

# BGM（残った1曲）をリネームして移動
mv "$HOME/Desktop/BGM_candidate_*.mp3" "$DRIVE/audio/ep{NNN}-BGM.mp3"
```

移動完了を報告する。

---

## STEP 5 — 素材を自動生成する

以下を実行する：

```bash
python3 sc_tts_gen.py --episode ep{NNN}                    # ナレーション音声生成
python3 sc_image_gen.py --episode ep{NNN}                  # 本編用画像生成（16:9）
python3 sc_image_gen.py --episode ep{NNN} --shorts         # Shorts用画像生成（9:16）
```

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

次のステップ:
  /sc-upload  # YouTube アップロード（本編・Shorts・字幕・即時公開）
```
