# /sc-upload — Samurai Chronicles YouTube アップロード

本編・Shorts・字幕を YouTube にアップロードするコマンド。

**デフォルト動作: 火・木・土曜の 03:00 JST に1本自動予約（2026-08-30〜、週3本）。**
複数エピソードが積まれている場合は次の配信曜日（火・木・土）に自動でずらす。
（03:00 JSTは米国側では前日昼頃にあたり、米国の平日・日中公開を意図した設計。
火木土＝米国側では月水金。制作リソース不足のため週5本〈火〜土〉から変更。）

## 認証

Lamps Whisper と同じ認証ファイルを使用:
- `~/.claude/secrets/yt_client_secrets.json`
- `~/.claude/secrets/yt_token.json`（初回認証後に自動生成）

---

## STEP 1 — エピソード番号を確認する

ユーザーにエピソード番号を聞く（例: 1、001、ep001 などどの形式でも受け付ける）。
内部では `ep001` 形式に正規化する。

**Desktopフォルダの扱い（2026-08-25〜）:** `/sc-new` STEP 6完了後、`~/Desktop/SC/` に
確認用コピー（サムネイル・BGM・完成動画）が残っている場合がある。ユーザーが `/sc-upload` を
明示的に実行した時点で「動画を確認しOKした」とみなし、動画確認への個別のOK待ちは行わない
（`/sc-upload` の起動自体が確認完了の意思表示のため）。

`rm -rf "$HOME/Desktop/SC"` を実行する**前に必ず**、Google Drive側に該当エピソードの
必要ファイルが揃っていることを確認する（削除後に不足が発覚すると復旧できないため）：
```bash
DRIVE="$HOME/Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles/ep{NNN}"
ls "$DRIVE/images" | wc -l          # 本編シーン画像（通常20枚）
ls "$DRIVE/images_shorts" | wc -l   # Shorts画像
ls "$DRIVE/audio" | wc -l           # 音声（シーン数+teaser+shorts）
ls "$DRIVE/output"                  # 本編mp4・shortsmp4・srtの3点
ls "$DRIVE" | grep -E "thumbnail|制作確認書"
```
件数がSTEP5C統合確認時点の想定と大きく食い違う、またはファイルが見当たらない場合は
削除を中止し、先にDriveへの登録・コピー漏れを解消してからクリーンアップする。
確認できたら `rm -rf "$HOME/Desktop/SC"` でクリーンアップしてよい。

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

**2026-09-06〜: `topics_queue.json` の `status` を自動更新（Fable監査対応）。**
アップロード成功後、`update_queue_status()` が該当 `episode_id` のエントリを
`"in_production"` → `"published"` に更新する（`last_updated` も更新）。以前はこの
更新が行われず、公開済みエピソードをキューから判別できなかった。

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

**サムネイルA/Bテスト（2026-09-06追加・Fable監査対応）:** `/sc-new` STEP3Bで生成した
サムネイル案A（`ep{NNN}_thumbnail_a.png`）はAPI経由で自動アップロードされる。
案B（`ep{NNN}_thumbnail_b.png`）はYouTube Data APIでは追加できない（YouTube Studioの
「テストと比較」機能はStudio UI専用でAPIが存在しない）ため、`sc_sns_up.py`実行後、
案Bのパスが完了報告に表示される。**ユーザーがYouTube Studioを開き、動画の
「詳細」→「サムネイル」→「テストと比較」から手動で案Bを追加する。** この手順は自動化できない。

## STEP 4 — コミット・プッシュ確認（2026-07-29〜: 自動化済み）

`sc_sns_up.py` は `run()` の末尾（サイト再ビルド後）で `commit_remaining_changes()` を実行し、
`git status --porcelain` に差分があれば（`episodes/ep{NNN}.json` の更新、`character_playlists.json`、
`index.html`/`episodes.html`/`playlists.html` の再ビルド分など）自動でまとめてコミット・pushする。
そのため STEP 2 のアップロード実行が成功していれば、このステップで手動コミットする必要は
通常ない（lamp-whisper の `sns_up.py` に実装済みの同等の仕組みを移植したもの）。

STEP 3 の完了報告後、念のため `git status` で作業ツリーがクリーンか確認する：

```bash
git status --short
```

**差分が残っている場合のみ**（自動コミットが何らかの理由で走らなかった場合のフォールバック）、
手動でコミット・pushする：

```bash
git add episodes/ep{NNN}.json characters/*.txt bgm_library.json topics_queue.json
git commit -m "$(cat <<'EOF'
feat: ep{NNN}（{person}）を制作・アップロード

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push
```

- `characters/*.txt` は今回新規追加されたキャラクター定義のみが対象（既存キャラのみの場合は変更なしなので自動的に含まれない）
- push 失敗時（リモートが進んでいる等）はユーザーに状況を報告し、対応を確認する

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
