# /sc-upload — Samurai Chronicles YouTube アップロード

本編・Shorts・字幕を YouTube にアップロードするコマンド。
アップロード後は即時公開される。

## 認証

Lamps Whisper と同じ認証ファイルを使用:
- `~/.claude/secrets/yt_client_secrets.json`
- `~/.claude/secrets/yt_token.json`（初回認証後に自動生成）

---

## STEP 1 — エピソード番号を確認する

ユーザーにエピソード番号を聞く（例: 1、001、ep001 などどの形式でも受け付ける）。
内部では `ep001` 形式に正規化する。

## STEP 2 — アップロード実行

```bash
python3 /Users/claude/samurai-chronicles/sc_sns_up.py --episode ep{NNN}
```

アップロード内容:
- 本編動画 + 字幕（SRT）
- Shorts動画（タイトルに #Shorts を付加）

## STEP 3 — 完了報告

```
✓ アップロード完了（公開）
  本編:   https://youtu.be/{VIDEO_ID}
  Shorts: https://youtu.be/{SHORTS_ID}
```
