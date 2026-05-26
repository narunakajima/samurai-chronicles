# Samurai Chronicles — プロジェクト憲法

## このプロジェクトについて

**Samurai Chronicles** は日本史をテーマにした英語 YouTube チャンネルの制作リポジトリ。
ターゲット: 海外の歴史好き。スタイル: BBC/Netflix ドキュメンタリー調。

> **重要:** このリポジトリは Samurai Chronicles 専用。`ランプの独り言` など他プロジェクトの
> 仕様・スタイル・ワークフローを混入させないこと。
> `lamp-whisper/` リポジトリは `freesound_download.py` を借用するためだけに参照する。

---

## ディレクトリ構成

```
samurai-chronicles/
├── episodes/           エピソード JSON（ep001.json〜）
├── characters/         キャラクター外見定義テキスト
├── .claude/commands/   スラッシュコマンド（sc-new, sc-upload など）
├── sc_video_gen.py     動画生成（Ken Burns + クロスフェード + BGM ミックス）
├── sc_subtitle_gen.py  字幕（SRT）生成
├── sc_tts_gen.py       ナレーション音声生成（TTS）
├── sc_image_gen.py     シーン画像生成（Gemini）
├── sc_inject_bgm_credit.py  CC BY クレジット自動注入
├── sc_review_gen.py    制作確認書生成
└── topics_queue.json   制作キュー
```

素材（音声・画像・出力動画）は Google Drive に保存:
```
~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/
└── ep{NNN}/
    ├── audio/        S01.wav〜S20.wav, S00_teaser.wav, S00_shorts.wav, ep{NNN}-BGM.mp3
    ├── images/       S01.png〜S20.png（16:9）
    ├── images_shorts/ S01.png〜S20.png（9:16）
    └── output/       Samurai Chronicles ep{NNN}.mp4, ep{NNN}_shorts.mp4, ep{NNN}.srt
```

---

## 主要定数（sc_video_gen.py）

| 定数 | 値 | 説明 |
|---|---|---|
| `NARR_DELAY` | 0.5s | ナレーション開始前余白 |
| `NARR_TAIL` | 1.0s | ナレーション終了後余白 |
| `MIN_CLIP_FLOOR` | 5.0s | 音声ありシーンの最低クリップ尺 |
| `CROSSFADE_DURATION` | 0.8s | シーン間クロスフェード |
| `INTRO_DURATION` | 5.0s | チャンネルイントロ尺 |
| `TEASER_MAX_CLIPS` | 12 | テイザー最大クリップ数 |
| `BGM_VOLUME` | 0.12 | BGM音量 |

クリップ尺の決定ロジック:
- 音声あり: `max(MIN_CLIP_FLOOR, narr_dur + NARR_DELAY + NARR_TAIL)`
- 音声なし: `duration_seconds`（JSON値、フォールバック専用）

---

## エピソード制作フロー

```
/sc-new → TTS生成 → 画像生成 → 動画生成 → 字幕生成 → /sc-upload
```

スラッシュコマンド一覧:
- `/sc-new`    新エピソード生成（JSON・確認書・サムネイル・BGM）
- `/sc-review` 制作確認書 + BGM選択の確認
- `/sc-upload` YouTube アップロード（本編・Shorts・字幕）
- `/sc-bgm`    BGMピッカー

---

## BGM ルール

- **必ず重厚なオーケストラ調**に限定する
- クエリに `orchestral` / `epic` / `cinematic` のいずれかを必須含む
- 禁止: shamisen単体, piano単体, ambient, folk, traditional, calm, nature 系

---

## コーディング規約

- Python 3.11+、外部ライブラリは最小限
- FFmpeg フィルターは文字列結合で組み立て（f-string）
- エラー時は `sys.exit(1)` で即終了
- 定数はファイル上部にまとめる
