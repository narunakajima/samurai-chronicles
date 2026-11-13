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
ls "$DRIVE/learning"                 # 学習版（Tokio モードの回）: mp3・mp4・thumbnail・short の4点
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

**完了報告の最後に、次の制作の前に `/clear` で会話を整理し、`/sc-new`（STEP 0 の `git pull` から始まる）を実行することを
ユーザーに一言勧める**（2026-10-16〜。長い会話のままだと古い経緯を引きずるため）。

## STEP 3.5 — Shortsの「関連動画」（2026-11-14〜: クラウド自動設定に移行。手動設定は廃止）

Shortsの「関連動画」（本編への誘導）は、**公開後に Muse（クラウド）が公開10分後に自動で設定する**。
`/sc-upload` の中では設定しない（Chrome も開かない・チャンネル切り替えもしない）。
Muse 側の自動設定が ep120（本編・学習版）で2回成功し、停止条件を満たしたため、
手動の保険工程と iMac のタイマー（`com.naru.sc-related-timer`）は撤去した
（plist は `~/Library/LaunchAgents/com.naru.sc-related-timer.plist.disabled-20261114` に改名して保管。戻すときは改名を戻して `launchctl bootstrap`）。

- 設定の記録（`episodes/ep{NNN}.json` の `related_video_set`）は自動処理側が更新する。
- 公開後に Muse の設定が失敗していた場合だけ、完了報告に書いてユーザーに伝える（その場で手動設定はしない）。

## STEP 3.6 — 未返信コメントに英語で返信する（2026-10-20追加）

アップロード後（STEP 3.5 の後）、チャンネル（`UCN1-TUxX_2UumGm3OKpmncg`）の**未返信コメント**に、
**確認なしで英語で**返信する。定型ではなく、コメント内容に合わせて Claude が1件ずつ書く。

1. 取得: `python3 sc_comment_reply.py list`（JSON。`thread_id`・動画タイトル・投稿者・本文）。空なら終了。
2. 返信文はコミュニティ担当 `sc-community`（`subagent_type: "sc-community"`、`model: "sonnet"`）に書かせる（2026-10-27〜、担当者制）。
   依頼文には、`list` の出力JSONのパス、保存先（スクラッチパッドの `{"thread_id": "reply text"}` のJSON）、下の「返信の方針」全文を書く。
   終わったら `python3 team_log.py add --agent sc-community --episode ep{NNN} --step 3.6 --result ok --note "返信N件・見送りN件"` で記録する。
3. 投稿: `python3 sc_comment_reply.py post <JSONパス>`（返信済みIDは `data/comment_replies.json` に記録。STEP 4 のコミットに含まれる）。

**返信の方針（無難第一）:**
- 英語、1〜2文、丁寧で温かいトーン。視聴・コメントへの感謝＋コメント内容に軽く触れる程度。
  コメントが英語以外なら、その言語が確実に分かる場合のみ同じ言語で、不安なら英語で感謝だけ返す。
- 例: 感想→"Thank you for watching! Glad the story of ○○ resonated with you."／
  補足・ツッコミ→"Thanks for adding that, much appreciated."／応援→感謝のみ。
- **書かないこと:** 動画にない史実・年号・数字の断言や新しい歴史解釈の主張、今後の動画の約束、
  政治・宗教・現代の国家間問題などへの立場表明、他者・他チャンネルの批評、絵文字の乱用（使っても1つまで）。
- **返信せずに見送る（完了報告で本文と理由を日本語で伝える）:** スパム・宣伝・詐欺っぽいリンク、
  誹謗中傷・ヘイト、史実の誤り指摘、歴史の詳しい質問で無難に答えられないもの。
  これらは `post` のJSONに含めない（次回も未返信として残るので、ユーザーが判断できる）。
- 史実の誤りを指摘するコメントは、返信せずに必ずユーザーへ報告する。
- 失敗してもアップロード自体には影響しない。

---

## STEP 3.7 — 学習版（英語で聴く日本史）の公開・関連動画・コメント返信（2026-10-23追加）

**この STEP でやることは3つ。タイミングが別々なので注意（2026-10-25 整理）:**

| やること | 対象の回 | タイミング |
|---|---|---|
| ① 学習版のアップロード（公開予定） | 今回の回（公開 OK 済みのもの） | STEP 2 の直後。SC が未公開でもよい。SC の公開日の **07:00 JST** に公開予定 |
| ② ショートの関連動画の設定 | （手動では行わない） | 公開後に Muse（クラウド）が公開10分後に自動設定する（2026-11-14〜） |
| ③ コメント返信（日本語） | 学習版チャンネルの未返信コメント | 毎回 |

学習版そのもの（音声・動画・サムネイル・ショート）は `/sc-learn` で、本編の動画の確認 OK のあとに作り済み。この STEP では作らない。
学習版は別チャンネル「英語で聴く日本史」（`UCWOFhTRNmbVeVWgwF9DfoNA`、`@eigo-de-nihonshi`）。制作は `/sc-learn`（本編の動画の確認 OK のあと）。
公開してよいのは、**ユーザーが事前に OK を出した回だけ**（`learn_targets.py --approve`）。手順書: `learning/YOUTUBE_SETUP.md`。

### 手順

1. 対象を出す:
   ```bash
   python3 learning/learn_targets.py
   ```
   - 「アップロード対象」: 学習版の公開 OK があり、まだ上げていない回（SC が未公開でもよい。公開日時は SC 本編に合わせる）
   - 「待ち」: 学習版はあるが、SC が未公開か、公開 OK がない回（参考。ユーザーに伝えるだけ。勝手に公開しない）
   「アップロード対象」が 0 件でも、手順4（コメント返信）は行う。

2. アップロード（**SC の公開日の 07:00 JST に公開予定**。本編・サムネイル・ショートを一緒に上げる）。対象の回ごとに、公開日時は **SC の公開日の 07:00 JST**（SC の `scheduled_at` の4時間後。`learn_targets.py` が `scheduled_at` を表示する）:
   ```bash
   cd learning && python3 learn_upload.py ep{NNN} --publish-at "{SC の公開日} 07:00"
   ```
   認証したチャンネルが学習版でなければ止まる。成功すると `learning/uploads/ep{NNN}.json` に動画 ID が残る。
   ユーザーが動画を確認して OK を出したあとなので、予約公開にしてよい。すでにアップ済みの回の公開日時を変えるときは `python3 learn_upload.py ep{NNN} --schedule-existing --publish-at "{日付} 07:00"`（過ぎていればその場で公開）。
   失敗（認証・容量など）した回は、理由を完了報告に書いて次へ進む（SC のアップロードには影響しない）。

3. ショートの関連動画: **この STEP では設定しない**。公開後に Muse（クラウド）が公開10分後に自動で設定する（STEP 3.5 の注記のとおり。2026-11-14〜）。

4. 学習版チャンネルの未返信コメントに**日本語で**返信する（**確認なしで**。STEP 3.6 と同じ進め方）:
   ```bash
   python3 learning/learn_comment_reply.py list                     # 未返信コメントを JSON で出力
   python3 learning/learn_comment_reply.py post <JSONパス>           # {"thread_id": "返信文"} を投稿
   ```
   返信文は STEP 3.6 と同じく SCチーム コミュニティ担当 ソフィー（`sc-community`） に書かせる（依頼文に「日本語で」と、この手順の方針を書く。記録は `--step 3.7`）。
   返信の方針は STEP 3.6 の「無難第一」と同じ（日本語、1〜2文、丁寧で温かく。視聴・コメントへの感謝＋内容に軽く触れる程度。
   書かないこと・見送るものも STEP 3.6 のとおり。英語の表現や発音についての質問で、無難に答えられないものは見送る）。
   返信済みは `data/learn_comment_replies.json` に残る。

5. 完了報告に、アップロードした回（URL）・返信した件数・見送ったコメント・待ちの回（理由つき）を書く。
   `learning/uploads/ep*.json` と `data/learn_comment_replies.json` に変更が出るので、STEP 4 で一緒にコミットする。

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
git add -u episodes/   # STEP 3.5 の related_video_set の更新分（追跡済みのファイルのみ。制作中の未追跡エピソードは含めない）
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
