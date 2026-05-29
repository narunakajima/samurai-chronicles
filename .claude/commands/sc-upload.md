# /sc-upload — Samurai Chronicles YouTube アップロード

本編・Shorts・字幕を YouTube にアップロードするコマンド。

**デフォルト動作: 毎日 03:00 JST に1本自動予約。**
複数エピソードが積まれている場合は翌日以降に自動でずらす。

## 認証

Lamps Whisper と同じ認証ファイルを使用:
- `~/.claude/secrets/yt_client_secrets.json`
- `~/.claude/secrets/yt_token.json`（初回認証後に自動生成）

---

## STEP 1 — エピソード番号を確認する

ユーザーにエピソード番号を聞く（例: 1、001、ep001 などどの形式でも受け付ける）。
内部では `ep001` 形式に正規化する。

特別な指定がある場合のみ追加オプションを使用:
- 「今すぐ公開」「即時」→ `--now`
- 「○月○日 ○時に公開」→ `--publish-at "YYYY-MM-DD HH:MM"`

## STEP 2 — アップロード実行

**通常（03:00 JST 自動予約）:**
```bash
python3 $HOME/samurai-chronicles/sc_sns_up.py --episode ep{NNN}
```

**即時公開:**
```bash
python3 $HOME/samurai-chronicles/sc_sns_up.py --episode ep{NNN} --now
```

**日時を手動指定（JST）:**
```bash
python3 $HOME/samurai-chronicles/sc_sns_up.py --episode ep{NNN} --publish-at "2026-06-01 20:00"
```

アップロード内容:
- 本編動画 + 字幕（SRT）
- Shorts動画（タイトルに #Shorts を付加）
- 予約の場合: 本編・Shorts ともに同じ日時で予約される

スロット割り当てロジック:
1. `episodes/*.json` の `scheduled_at` を読んで使用済み日付を収集
2. 今日の 03:00 JST がまだ未来 → 今日を候補に
3. 過ぎている or 使用済み → 翌日以降の空き日を自動で割り当て

## STEP 3 — 完了報告

```
✓ アップロード完了（予約公開: 2026-06-01 03:00 JST（自動））
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
