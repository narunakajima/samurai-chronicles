# /sc-upload — Samurai Chronicles YouTube アップロード

本編・Shorts・字幕を YouTube にアップロードするコマンド。
公開日時を指定すれば予約投稿、省略すれば即時公開。

## 認証

Lamps Whisper と同じ認証ファイルを使用:
- `~/.claude/secrets/yt_client_secrets.json`
- `~/.claude/secrets/yt_token.json`（初回認証後に自動生成）

---

## STEP 1 — エピソード番号と公開日時を確認する

ユーザーにエピソード番号を聞く（例: 1、001、ep001 などどの形式でも受け付ける）。
内部では `ep001` 形式に正規化する。

公開日時の指定がある場合（例：「明日の20時」「6/1 夜8時」）は JST として解釈し、
`--publish-at` に渡す文字列に変換する（例: `"2026-06-01 20:00"`）。

## STEP 2 — アップロード実行

**即時公開（日時指定なし）:**
```bash
python3 $HOME/samurai-chronicles/sc_sns_up.py --episode ep{NNN}
```

**予約公開（日時指定あり）:**
```bash
python3 $HOME/samurai-chronicles/sc_sns_up.py --episode ep{NNN} --publish-at "2026-06-01 20:00"
```

アップロード内容:
- 本編動画 + 字幕（SRT）
- Shorts動画（タイトルに #Shorts を付加）
- 予約の場合: 本編・Shorts ともに同じ日時で予約される

## STEP 3 — 完了報告

**即時公開の場合:**
```
✓ アップロード完了（即時公開）
  本編:   https://youtu.be/{VIDEO_ID}
  Shorts: https://youtu.be/{SHORTS_ID}
```

**予約公開の場合:**
```
✓ アップロード完了（予約公開: 2026-06-01 20:00 JST）
  本編:   https://youtu.be/{VIDEO_ID}
  Shorts: https://youtu.be/{SHORTS_ID}
  ※ 指定日時まで非公開状態です。YouTube Studio で確認できます。
```

---

## 自動処理: キャラクタープレイリスト管理

`sc_sns_up.py` はアップロード後に `sc_playlist_manager.py` を自動呼び出しする。
状態は `character_playlists.json` に保存される。

### プレイリスト作成ルール

| 登場回数 | 処理 |
|---|---|
| 初登場（1回目） | `character_playlists.json` に記録のみ。プレイリストは作成しない |
| 2回目 | YouTube にプレイリストを新規作成 → 出演済み全エピソードを追加 |
| 3回目以降 | 既存プレイリストに今回のエピソードを追加 |

プレイリストタイトル形式: `"CHARACTER NAME | Samurai Chronicles"`

### 対象キャラクター

エピソードJSON の各シーン `character_ref` フィールドから自動抽出。
`characters/` フォルダに定義されているキャラクターが対象。
