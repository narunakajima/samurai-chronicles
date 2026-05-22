# /sc-bgm — Samurai Chronicles BGMピッカー

エピソードJSONを読み込み、Freesound からムードに合った BGM を 3 曲ダウンロード。ユーザーが 1 曲に絞るまで繰り返し、最終的にエピソードフォルダへ保存する。

## 定数

- エピソードフォルダ: `~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/`
- デスクトップ: `~/Desktop/`
- スクリプト: `/Users/claude/.claude/scripts/freesound_download.py`

## 手順

### STEP 1 — エピソード番号を確認する

ユーザーにエピソード番号を聞く（例: 1、001、ep001 などどの形式でも受け付ける）。
内部では `ep001` 形式に正規化し、フォルダパスを組み立てる:
`~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}/`

### STEP 2 — エピソードJSONを読んでムードを把握する

`/Users/claude/samurai-chronicles/episodes/ep{NNN}.json` を読み込む。

以下を抽出してBGMのムードを決める:
- `episode_title`（エピソードのテーマ）
- 各シーンの `type`（hook / setup / climax / insight など）
- 各シーンの `narration` の雰囲気（緊張感、壮大さ、悲劇性など）

これらを組み合わせて **2〜3語の英語クエリを3本** 生成する（1スロット1クエリ）。
長いクエリは0件になるため必ず短く保つ。

**禁止キーワード（環境音・自然音・SE系は除外）:**
forest, rain, nature, field recording, ambience, birdsong, wind, wave, cricket など。
必ず楽器・音楽系キーワードに絞る（orchestral, strings, piano, taiko, shamisen, cinematic, epic など）。

例（ep001「武蔵 vs 小次郎」の場合）:
- q1: `orchestral dramatic cinematic`
- q2: `epic strings tension`
- q3: `japanese koto shamisen`

### STEP 3 — Freesound から 3 曲ダウンロードする

ラウンド変数を `ROUND=0` で初期化し、以下を実行する:

```bash
FREESOUND_API_KEY=$FREESOUND_API_KEY python3 /Users/claude/.claude/scripts/freesound_download.py \
  "<Q1>" "<Q2>" "<Q3>" \
  "$HOME/Desktop/" \
  --round $ROUND
```

- 再試行のたびに `ROUND` を1増やす（同じ曲が出ないよう seen_ids で管理済み）
- ダウンロードした 3 ファイルの名前・尺・ライセンスをユーザーに伝える

### STEP 4 — ユーザーに確認を求める

「3 曲をデスクトップに保存しました。気に入った 1 曲だけ残して、残り 2 曲は削除してください。終わったら教えてください。」と伝える。

### STEP 5 — 残っているファイル数を確認する

```bash
ls ~/Desktop/BGM_candidate_*.mp3 2>/dev/null | wc -l
```

ファイル数が 1 の場合 → STEP 6 へ  
ファイル数が 0 の場合 → 「ファイルが見つかりません。削除しすぎていないか確認してください」と伝えて STEP 4 に戻る  
ファイル数が 2 以上の場合 → 「まだ複数残っています。1 曲だけ残してください」と伝えて STEP 4 に戻る

ユーザーが「NG」または「もう 3 曲ほしい」と言った場合 → デスクトップの候補を削除し `ROUND += 1` して STEP 3 に戻る

### STEP 6 — ファイルをリネームしてエピソードフォルダへ移動する

残ったファイルを特定し、以下を実行する:

```bash
SRC=$(ls ~/Desktop/BGM_candidate_*.mp3)
DEST="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}/audio/ep{NNN}-BGM.mp3"
mkdir -p "$(dirname "$DEST")"
mv "$SRC" "$DEST"
echo "Moved: $DEST"
```

完了を報告する: 「`ep{NNN}-BGM.mp3` をエピソードフォルダに保存しました。」

## エラー対応

- `FREESOUND_API_KEY` が空の場合: 「settings.json に FREESOUND_API_KEY が設定されていません」と伝えて終了する
- エピソードJSONが見つからない場合: `/Users/claude/samurai-chronicles/episodes/` のファイル一覧を表示する
- Freesound 検索結果が 0 件の場合: クエリを英語でシンプルにして再試行する
