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

## STEP 3.5 — Shortsの「関連動画」を設定する（Chromeを自動操作、2026-10-02追加）

Shortsの「関連動画」に本編を設定しておくと、Shortsの視聴者を本編へ誘導できる。
`sc_sns_up.py` からは設定していない（YouTube Data APIで設定できるかは未確認）ため、
Claude in Chrome（ユーザーのログイン済みChrome。内蔵ブラウザはログインが必要で使えない）で
操作する。kagaku-life の `/kl-upload` STEP 3.5 と同じ仕組み。

**重要な制約: Studioの関連動画の選択画面には「公開済みの動画」しか出ない。**
STEP 2で予約したばかりの本編は公開日（03:00 JST）まで選べないので、今回アップロードした回は
この時点では設定できない。そこで「公開日時を過ぎていて、まだ設定していないエピソード」を
全てまとめて対象にする（前回までに予約した回が、公開された後の `/sc-upload` で拾われる）。
完了の記録は `episodes/ep{NNN}.json` の `related_video_set: true`。

### 手順

1. 対象を出す:
   ```bash
   python3 sc_related_targets.py
   ```
   「設定が必要なShortsはありません」なら、このSTEPは終了（今回の回は公開後の
   `/sc-upload` で設定される、と完了報告に一言添える）。Chromeは開かない。
   検索語は、他のエピソードのタイトルに含まれない最短の先頭部分が自動で選ばれる
   （SCのタイトルは英語で先頭が似たものが多いため）。

2. Chromeを用意する。**起動時点でChromeが動いていたかを必ず記録する**:
   ```bash
   pgrep -x "Google Chrome" >/dev/null && echo running || echo not-running
   ```
   `not-running` なら `open -a "Google Chrome"` で起動する（この場合は最後に終了する）。
   `list_connected_browsers` でClaude in Chrome拡張の接続を確認する（起動直後は数十秒かかる
   ことがある）。接続できなければ、このSTEPは諦めて完了報告にその旨を書く（Chromeは
   自分で起動していた場合のみ終了する）。ツールが未読込なら `ToolSearch` で
   `mcp__claude-in-chrome__*`（`browser_batch`・`computer`・`navigate`・`tabs_context_mcp` 等）を
   まとめて読み込む。

3. チャンネルを切り替える。Chromeは通常、別チャンネル（ランプのひとりごと等）でログインして
   いる。アバター → 「アカウントを切り替える」で **「Samurai Chronicles」
   （@Samurai-Chronicles-JP、チャンネルID `UCN1-TUxX_2UumGm3OKpmncg`）** を選ぶ。切り替え前に
   表示されていたチャンネルを覚えておき、**最後に必ず元に戻す**。切り替え後、
   `studio.youtube.com/channel/` のURLが上記のIDになっていることを確認する。
   **他チャンネルの動画は絶対に編集しない。**

4. 対象のShortsごとに（`sc_related_targets.py` が出した shorts ID・検索語を使う）。
   **座標クリックは使わない**（ウィンドウサイズが操作ごとに変わり、2026-10-02にクリックが外れた）。
   ページ内のスクリプト `studio_related_video.js` を `javascript_tool` で実行する:
   1. 最初に1回だけ、スクリプトの「関数本体」（`return (async()=>{ ... })()` の部分）を
      StudioのページのlocalStorageに保存する:
      `localStorage.setItem('rel_fn', `<関数本体>`)`
   2. 1本ごとに `studio.youtube.com/video/{SHORTS_ID}/edit` を開き（未保存の変更があると
      「Leave site?」が出るので `navigate` は `force: true`）、3秒待ってから実行する:
      `await (new Function('KW','FORCE',localStorage.getItem('rel_fn')))("検索語", false)`
      複数本は `browser_batch` に「navigate → wait 3 → javascript_tool」を並べると速い
      （1バッチ6〜8本。接続が切れて途中で止まることがあるが、実行は何度やっても安全な
      作りで、設定済みなら `skip:'already'` で飛ばす）。
   3. スクリプトがやること: 現在の関連動画が「なし」でなければ何もしない（`skip:'already'`、
      `before` が現在値）／「子ども向けか」が**未選択のときだけ**「いいえ、子ども向けでは
      ありません」を選ぶ（選択済みの値は書き換えない）／関連動画の選択画面で検索語に合う
      **本編**（`#Shorts` が付かない方）を選ぶ／「保存」を押す。
      結果は `{id, kid, before, label, rel, saved}` のJSONで返る。
   4. **確認する**: `skip` だった回は `before` が**その回の本編のタイトルと一致するか**見る。
      一致しなければ取り違えなので、`FORCE=true` で再実行して上書きする（SCのep016で
      別の回の本編が設定されていた実例がある）。`err:'no-option'` の回（検索語に合う本編が
      ない）はスキップして報告する。保存後は読み込み直して、関連動画欄が本編のタイトルで
      あることを確かめる（`saved` の値だけに頼らない。`saved:false` でも保存されていた例がある）。
      確認できた回だけ `python3 sc_related_targets.py --mark ep{NNN}`。
   5. 全部終わったら `localStorage.removeItem('rel_fn')` で片付ける。
   - 関連動画以外の設定（公開日時・タイトル・説明・字幕など）は変更しない。
   - 想定と違うUI（要素が見つからない等）で `err` が続く場合は、無理に操作せずそのSTEPを
     中断して報告する。
   - 件数が多い回（初回の遡及など）は、10本ほどずつバッチにして途中経過を報告する。


5. 後片付け（**必ずこの順**）:
   1. アカウントを**元のチャンネルに戻す**（手順3で覚えたもの）。
   2. 自分で開いたタブ（MCPのタブグループ内）を閉じる。
   3. **手順2で自分がChromeを起動した場合のみ**、Chromeを終了する:
      ```bash
      osascript -e 'quit app "Google Chrome"'
      ```
      **すでにChromeが動いていた場合は終了しない**（ユーザーが他のタブ・作業を開いている
      ため）。自分が開いたタブを閉じるだけにして、完了報告に「Chromeは元から開いて
      いたので終了していません」と書く。

6. 完了報告に、設定した件数・スキップした回（理由つき）・Chromeを終了したかを書く。
   `episodes/ep*.json` に `related_video_set` の変更が出るので、STEP 4で一緒にコミットする。

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
