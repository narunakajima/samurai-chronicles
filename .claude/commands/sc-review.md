# /sc-review — Samurai Chronicles 制作確認（BGM + 確認書）

動画生成前の最終確認ステップ。
BGM候補3曲のダウンロードと制作確認書の生成を同時に行い、
ユーザーがデスクトップで両方を確認してOKを出したら動画生成に進む。

## 定数

- エピソードフォルダ: `~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/`
- デスクトップ: `~/Desktop/`
- スクリプト（確認書）: `$HOME/samurai-chronicles/sc_review_gen.py`
- スクリプト（BGM）: `$HOME/.claude/scripts/freesound_download.py`

## 手順

### STEP 1 — エピソード番号を確認する

ユーザーにエピソード番号を聞く（例: 1、001、ep001 などどの形式でも受け付ける）。
内部では `ep001` 形式に正規化する。

### STEP 2 — エピソードJSONを読んでBGMクエリを準備する

`$HOME/samurai-chronicles/episodes/ep{NNN}.json` を読み込む。

以下を抽出してBGMムードを把握し、**2〜3語の英語クエリを3本** 生成する:
- `episode_title`
- 各シーンの `type` と `narration` の雰囲気（緊張感、壮大さ、悲劇性など）

**禁止キーワード:** forest, rain, nature, field recording, ambience, birdsong, wind, wave, cricket など環境音・SE系は除外。
楽器・音楽系キーワードのみ（orchestral, strings, piano, taiko, shamisen, cinematic, epic など）。

### STEP 3 — BGM候補ダウンロードと確認書生成を同時実行

以下の2つをバックグラウンドで並行実行する:

**A) BGM候補3曲をデスクトップにダウンロード:**
```bash
ROUND=0
FREESOUND_API_KEY=$FREESOUND_API_KEY python3 $HOME/.claude/scripts/freesound_download.py \
  "<Q1>" "<Q2>" "<Q3>" \
  "$HOME/Desktop/" \
  --round $ROUND
```


**B) 制作確認書を生成:**
```bash
python3 $HOME/samurai-chronicles/sc_review_gen.py --episode ep{NNN}
```

両方が完了したらユーザーに通知する:
「デスクトップに以下を保存しました:
  - BGM候補3曲（BGM_candidate_01〜03.mp3）
  - 制作確認書（ep{NNN}_制作確認書.txt）

BGMを試聴して1曲だけ残してください。確認書も合わせてご確認ください。
問題なければ「OK」または選んだBGM番号（例: 2）を教えてください。」

### STEP 4 — ユーザーの確認を待つ

ユーザーが以下を完了するまで待機:
1. 確認書の内容チェック（ナレーション翻訳・ファクトチェック）
2. BGM試聴・2曲削除（1曲だけ残す）

「NG」または「もう3曲ほしい」と言った場合:
→ デスクトップの候補を削除し `ROUND += 1` してSTEP 3Aのみ再実行

確認書の内容に修正が必要な場合:
→ ep{NNN}.json の該当シーンを修正し、STEP 3Bを再実行

### STEP 5 — 残ったファイル数を確認する

```bash
ls ~/Desktop/BGM_candidate_*.mp3 2>/dev/null | wc -l
```

1ファイルの場合 → STEP 6へ
0または2以上の場合 → 「もう1曲だけ残してください」と伝えてSTEP 4に戻る

### STEP 6 — BGMをリネームしてエピソードフォルダへ移動

```bash
SRC=$(ls ~/Desktop/BGM_candidate_*.mp3)
DEST="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}/audio/ep{NNN}-BGM.mp3"
mkdir -p "$(dirname "$DEST")"
mv "$SRC" "$DEST"
echo "Moved: $DEST"
```

完了を報告:
「準備完了です。
  ✅ BGM: ep{NNN}-BGM.mp3 をエピソードフォルダに保存
  ✅ 確認書: 承認済み

動画生成を開始してよいですか？」

### STEP 7 — ユーザーのGOサインを待って動画生成

ユーザーが「はい」「OK」「GO」などを返したら:

```bash
python3 $HOME/samurai-chronicles/sc_video_gen.py --episode ep{NNN}
```

## エラー対応

- GEMINI_API_KEY が空: 確認書生成をスキップし、BGMのみ実行
- FREESOUND_API_KEY が空: 「settings.json にキーを設定してください」
- エピソードJSONが見つからない: `episodes/` のファイル一覧を表示
- 確認書生成中のAPIエラー: リトライ後、失敗した場合は手動確認を依頼
