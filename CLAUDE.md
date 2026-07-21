# Samurai Chronicles — プロジェクト憲法

## このプロジェクトについて

**Samurai Chronicles** は日本史をテーマにした英語 YouTube チャンネルの制作リポジトリ。
ターゲット: 海外の歴史好き。スタイル: BBC/Netflix ドキュメンタリー調。

> **重要:** このリポジトリは Samurai Chronicles 専用。`ランプの独り言` など他プロジェクトの
> 仕様・スタイル・ワークフローを混入させないこと。
> `lamp-whisper/` リポジトリは `freesound_download.py` を借用するためだけに参照する
> （`$HOME/lamp-whisper/freesound_download.py`。ダウンロード済み曲IDを
> `~/.claude/scripts/.freesound_seen_ids` に記録して重複DLを回避する `seen_ids` 機構に加え、
> `--library <path>` でライブラリの `source_id`/`source_name` と照合し既存BGMの再DLを防ぐ
> 機能を持つ。SC側から呼ぶ際は必ず `--library $HOME/samurai-chronicles/bgm_library.json`
> を指定し、SC自身のライブラリと突き合わせること）。

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
├── sc_bgm_library.py   BGMライブラリ管理（登録・紐付け）
├── bgm_library.json    BGMライブラリ台帳（パス・ライセンス・タグ・used_in）
└── topics_queue.json   制作キュー
```

素材（音声・画像・出力動画）は Google Drive に保存:
```
~/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/
├── BGM/              BGM集中管理フォルダ（{episode_id}-BGM.mp3。2026-06-01〜統一）
│                     複数エピソードで使い回し可能。bgm_library.json で台帳管理。
└── ep{NNN}/
    ├── audio/        S01.wav〜S20.wav, S00_teaser.wav, S00_shorts.wav
    │                 （BGMはここには置かない。BGM/ フォルダに集約する）
    ├── images/       S01.png〜S20.png（16:9）
    ├── images_shorts/ S01.png〜S20.png（9:16）
    └── output/       Samurai Chronicles ep{NNN}.mp4, ep{NNN}_shorts.mp4, ep{NNN}.srt
```

### BGM 参照優先順位（`sc_video_gen.py`）

**3曲構成（2026-07〜の標準）:** episode JSON の `bgm_sources` に
`{"intro": ..., "main": ..., "outro": ...}` が揃っていればそれを使う。
序盤（hook〜setup）・中盤（rising_action〜climax）・終盤（falling_action〜outro）の
境界はシーンタイプから自動計算し、`BGM_CROSSFADE`（4秒）でクロスフェードする。
新規曲は `BGM/{episode_id}-BGM-{role}.mp3` として保存される。
Shorts は3曲構成でも中盤（main）の1曲のみ使用。

**従来1曲方式（フォールバック）:** `bgm_sources` がない場合は以下の順で解決する。

1. `BGM/{episode_id}-BGM.mp3`（集中フォルダに直接ある場合）
2. episode JSON の `bgm_source` フィールド（ライブラリ曲を流用紐付け）
3. `bgm_library.json` の `used_in` 配列を逆引き

新規BGMは `/sc-new` STEP 4（役割別: Freesound新規3曲＋ライブラリ既存3曲の計6候補から
各役割1曲選定）の中で `sc_bgm_library.py --add --role <role>` により `BGM/` フォルダへ自動登録される。
既存ライブラリ曲を使い回す場合は `sc_bgm_library.py --use-library --role <role>` で `bgm_sources[role]` を設定する。

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
| `BGM_CROSSFADE` | 4.0s | 3曲構成時の曲間クロスフェード |

クリップ尺の決定ロジック:
- 音声あり: `max(MIN_CLIP_FLOOR, narr_dur + NARR_DELAY + NARR_TAIL)`
- 音声なし: `duration_seconds`（JSON値、フォールバック専用）

---

## エピソード制作フロー

```
/sc-new → TTS生成 → 画像生成 → 動画生成 → 字幕生成 → /sc-upload
```

スラッシュコマンド一覧:
- `/sc-new`    新エピソード生成（JSON・確認書・サムネイル・BGM選定を一括並行処理）
- `/sc-upload` YouTube アップロード（本編・Shorts・字幕）

> 旧 `/sc-bgm`（BGM単体ピッカー）・`/sc-review`（確認書+BGM）は
> `/sc-new` STEP 4 に機能統合されたため 2026-06 に削除した。

---

## S19（次回予告）ルール — キューとの自動連携

`/sc-new` STEP 2 でエピソードJSON を生成する際、S19（type: "teaser"）のナレーションを書く前に
必ず以下を実行する：

1. `topics_queue.json` を読み込み、**現在生成中のエピソードの次**に来る `status: "pending"` のエピソードを特定する
2. ユーザーに確認する：
   ```
   S19（次回予告）は以下のエピソードを予告します：
   ep{NNN+1}「{title}」（{era} / {priority}）
   これでよいですか？（はい / 別のエピソードを指定）
   ```
3. 確認が取れたらそのエピソードの内容でS19ナレーションを生成する

**目的:** S19の内容とキューの実際の次エピソードがずれることを防ぐ。
ep011→ep012 のような「テイザーとキューの不一致」を自動検出する。

---

## BGM ルール

- **必ず重厚なオーケストラ調**に限定する
- クエリに `orchestral` / `epic` / `cinematic` のいずれかを必須含む
- 禁止: shamisen単体, piano単体, ambient, folk, traditional, calm, nature 系

---

## マシン判定ルール

git操作（pull / push / status など）の前に必ず `hostname` でマシンを確認する。

| hostname | マシン |
|---|---|
| `naru-iMac.local` | iMac |
| それ以外 | MacBook（または別端末） |

ユーザーが「このマシンは〇〇です」と教えてくれた場合はその情報を優先する。
iPhone等のリモート接続からの操作でも、Claude Codeが動いているのはiMacなので `hostname` は `naru-iMac.local` になる。

---

## コーディング規約

- Python 3.11+、外部ライブラリは最小限
- FFmpeg フィルターは文字列結合で組み立て（f-string）
- エラー時は `sys.exit(1)` で即終了
- 定数はファイル上部にまとめる
