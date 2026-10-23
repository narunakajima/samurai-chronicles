# /sc-learn — Samurai Chronicles 学習版（日本語の英語耳トレーニング）

SC の英語エピソードから、日本人学習者向けの教材音声（約50分・1本）を作るコマンド。
規則の正本は `CLAUDE.md` の「学習版」の節。ここには手順を書く。

使い方: `/sc-learn ep106`（エピソード ID を指定する）

**対象:** 当面は Tokio モード（`"narrator": "tokio"`）のエピソード。訳が一人称（僕）の記者口調なので、従来方式（三人称）の回には合わない。

**実行のタイミング:** SC 本編の制作（動画生成・字幕生成）が終わったら、**続けて**実行する（2026-10-23 ユーザー決定）。
流れは `/sc-new → … → 字幕生成 → /sc-learn（台本・音声・動画・サムネイル・ショート）→ /sc-upload（SC を予約）`。

**公開はしない。** このコマンドは作って、ユーザーの確認を待つところまで。公開は、SC の本編が公開されたタイミングで行う（STEP 5）。

---

## STEP 0: 前提の確認

次がそろっているか確認する（欠けていれば、何が足りないかを報告して止める）。
- `episodes/ep{NNN}.json`（`narrator` が `tokio`）
- Drive の `ep{NNN}/audio/S01.wav〜`（シーン数ぶん。S00 は使わない）
- 環境変数 `GEMINI_API_KEY_SC` または `GEMINI_API_KEY`

## STEP 1: 台本（lessons/ep{NNN}.json）を書く

**Opus のサブエージェント**（`model: "opus"`、`subagent_type: "general-purpose"`）に任せる。
台本は、史実と英文の内容を正確に訳すものなので、SC の STEP 2A と同じく Opus に書かせる。

サブエージェントに渡すもの:
- `episodes/ep{NNN}.json` のフルパス（各シーンの `narration` が英文の正本）
- 見本: `learning/lessons/ep106.json`（形式と文体はこれに合わせる）
- 下の「台本の形式」と「台本の決まりごと」

### 台本の形式

```json
{
  "episode_id": "ep106",
  "title_ja": "織田信長 — 消えた遺体の謎",
  "display_map": {"おおた・ぎゅういち": "太田牛一", "神谷ときお": "神谷時生"},
  "intro":   ["段落1", "段落2", "..."],
  "scenes":  [{"scene": 1, "cue": "シーン1。見どころの説明。",
               "sentences": ["1文目の訳", "2文目の訳", "..."],
               "one_point": {"idx": 1, "phrase": "simply gone", "phrase_ja": "跡形もなく消えた",
                             "ja": "ワンポイント。このシンプリーは、…"}}],
  "to_full": "通しの前の案内",
  "closing": "締め"
}
```

英語の文は、`narration` を次の規則で分けたもの（`learning/clips.py` の `split_sentences`）:
`.` `?` `!` の後に空白、続いて大文字か引用符が来る所で区切る。`sentences` の訳は、この文と**同じ数・同じ順**にする。
文を確認するコマンド（`learning/` で実行）:

```bash
python3 -c "import json;from clips import split_sentences;e=json.load(open('../episodes/ep106.json'));[print(i+1,j+1,s) for i,sc in enumerate(e['scenes']) for j,s in enumerate(split_sentences(sc['narration']))]"
```

### 台本の決まりごと

- 語り手は Tokio の一人称（「僕」）。訳は意味を短く言い直すもの。解説・補足は足さない
- **訳は英文の内容を忠実に。** 史実の食い違いや、記録の「〜と伝えられる」といった留保も、英文のとおりに訳す
- 人名・地名など、読みが揺れる語は**かな書き**にする（例: みょうかくじ、おおた・ぎゅういち）。語り手の名前は「神谷ときお」
- **かな書きにした語は、`display_map` に「かな → 字幕用の漢字」を必ず登録する**（ナレーションはかな、字幕は漢字。2026-10-22 ユーザー指示）。
  短いかなは別の語の一部にも出るので、前後を含めて登録する（例: 「つる」は「まつる」にも含まれるので「つるが切れる」→「弦が切れる」）
- シーンの見どころ（`cue`）は、「シーンN。」で始め、**次に来る訳と同じ内容にしない**。注目点・位置づけ・日本語の慣用句が出る、など
- 訳が不要な文（締めの決まり文句の繰り返し等）は空文字 `""`（合図の音も鳴らない）
- **各シーンに `one_point`（使える英語表現）を1つ付ける**（2026-10-22 ユーザー指示）。`idx` はその表現を含む英文の番号（0始まり）、
  `phrase` は英文の中の表現そのまま（英文に含まれていること）、`phrase_ja` は画面のカードに出す意味、`ja` は Tokio の解説（「ワンポイント。」で始め、
  70〜90字。意味と使い方を短く。表現はカタカナで一度だけ触れてよい。正しい発音は、解説のあとに流れる本編の英文で聞かせる）
- 寺の名前（本能寺・阿弥陀寺 等）も読みが揺れる（「本能寺の変」を「ほんのうのへん」と読んだ）。台本では「ほんのうじ」のようにかなで書き、display_map に登録する
- 導入に、祖父の時計の細かい説明は書かない（シーン2の訳で語られる）。「歩きながら」など、聴く場面を決める文言も入れない
- 導入の第2段落は、進め方の説明（予告 → 合図の音 → 日本語の訳 → 英語の文 → 最後に通し）。ep106 の文面を踏襲する
- AI・生成に関する文言は、台本に書かない（公開時の表示は、別途ユーザーと決める）

### 台本の自己チェック（サブエージェントに実行させる）

- `sentences` の数が、英語の文の数と全シーンで一致している
- 「時生」が漢字のまま入っていない
- `cue` と最初の訳が、ほぼ同じ内容になっていない
- 英文の事実（日付・人名・数）を、訳が取り違えていない

## STEP 2: ビルド

`learning/` で、バックグラウンドで実行する。完了の判断は、完了フラグのファイルで行う（CLAUDE.md のコーディング規約を参照）。

```bash
cd learning && rm -f build/ep106.done && nohup sh -c 'python3 -u build_lesson.py ep106 > build_ep106.log 2>&1; echo $? > build/ep106.done' >/dev/null 2>&1 &
```

所要時間の目安: 初回は20〜30分（日本語音声の生成と読みの確認、英文の切り出し、単語の時刻）。
単語の時刻（動画の単語ハイライト用）は、手元の Whisper（openai-whisper、`~/.cache/whisper/small.pt`）で取る（`learning/words.py`）。ログに出る `⚠️` は、自動で作り直されているもの。
`learning/cache/` に保存されるので、台本の一部だけを直したときは、変えた部分だけが作り直される。
完了すると、Drive の `ep{NNN}/learning/` に mp3 が出力され、`learning/build/ep{NNN}/chapters.txt` に各パートの開始時刻が出る。

**止まったとき（`一致しません` が出た場合）:** 英文の切り出しの照合が合わなかった文。`learning/clips.py` の方式を変える前に、
まず文と書き起こしを見比べて、本当に切れ目が違うのか、書き起こしの聞き違いなのかを区別する。
CLAUDE.md の「Opus へのエスカレーション」の条件（同じ失敗が2回続く）に当たったら、Opus のサブエージェントに引き継ぐ。

## STEP 3: 確認（完成後に必ず行う）

自動チェックは、**固有名詞の読みに甘い**。完成した mp3 で次を確かめる（`learning/audio_check.py` で Gemini に聞かせる）:
- 語り手の名前が「ときお」と読まれている（導入・シーン1・シーン2・シーン20・締め）
- 人名・地名の読みが、かな書きどおりに読まれている（台本のかな書きの箇所を、いくつか抜き取る）
- 1シーンを抜き出して、「合図 → 日本語の訳 → 英語の文」の順に並んでいる

```bash
cd learning && python3 audio_check.py <音声ファイル> "日本語部分と英語部分を区別して順に書き起こして（英語は EN:、日本語は JA:）"
```

## STEP 3.5: 動画を作る

音声のビルド（STEP 2）が出力した `build/ep{NNN}/timeline.json` と手元の mp3 を使う。

```bash
cd learning && python3 build_video.py ep106 --preview 3:50 4:04   # 字幕の見た目だけ先に確かめる（数秒で出る）
cd learning && rm -f build/ep106.video.done && nohup sh -c 'python3 -u build_video.py ep106 > build_video_ep106.log 2>&1; echo $? > build/ep106.video.done' >/dev/null 2>&1 &
```

全編は約30分（背景のケンバーンズを含む。作ったケンバーンズは `build/ep{NNN}/kb/` に残り、字幕だけ直したときは使い回すので約13分）。出力は Drive の `ep{NNN}/learning/ep{NNN} {日本語タイトル}.mp4`。
確認: 長さが音声と同じこと（`ffprobe`）、いくつかの時刻のフレームを切り出して、字幕が帯からはみ出していないか・時刻どおりの場面かを目で見る。

## STEP 3.6: サムネイルとショート動画（毎回必ず作る）

目的は**学習版の本編に誘導すること**だけ。コンセプトは毎回共通（2026-10-23 ユーザー決定）:
「日本史を聴くだけで、英語が聞き取れるようになる（英語耳に）」をはっきり伝える。
共通の文言・レイアウト・流れは `learning/build_promo.py` に固定してあり、回ごとに変わる内容だけを台本の `promo` 欄に書く。

```json
"promo": {
  "thumb_scene": 1,                       // サムネイルの背景にするシーン（主役が大きく写る印象的な画像）
  "thumb_en": "Honnoji is burning.",      // サムネイルに見せる本編の英文（短い一文）
  "short": {
    "scene": 5, "idx": 4,                 // クイズの答えにする本編の英文（シーン番号と、文の番号 0始まり）
    "image_scene": 1,                     // 背景にする縦型の画像（images_shorts/ にあるもの）
    "quiz_title": "信長の「是非に及ばず」", // 画面の問い（字幕。漢字でよい）
    "quiz_ja": "信長の最後の言葉、ぜひにおよばず。英語で言えますか？",  // Tokio が読む問い（読みが揺れる語はかな）
    "phrase": "nothing could be done about it",  // 答えの英文の中の表現（英文に含まれていること）
    "phrase_ja": "是非に及ばず（どうしようもない）",
    "explain_ja": "どうしようもない、という意味の決まった言い方です。…"  // Tokio の一言解説（40〜60字）
  }
}
```

- クイズは「その回の有名な言葉・場面を、英語で言える？」の形にする（つかみ）。答えは本編の英文そのもの
- かな書きにした語は `display_map` にも登録する（字幕は漢字）

```bash
cd learning && python3 build_promo.py thumb ep106    # サムネイル（1280x720）
cd learning && python3 build_promo.py short ep106    # ショート（縦型、約40秒。2分ほどで出る）
```

出力は Drive の `ep{NNN}/learning/ep{NNN}_learning_thumbnail.png` と `ep{NNN}_learning_short.mp4`。
確認: サムネイルは主役の顔がコピーや Tokio に隠れていないか。ショートは場面ごとのフレームを切り出して、字幕・名札の位置を見る。

## STEP 4: ユーザーの確認

- 完成した mp3 のパスと、`chapters.txt` の内容（各パートの開始時刻）を報告する
- **ユーザーが聴いて OK を出すまで、公開に進まない。** 直しの依頼は、台本（`lessons/`）を直して STEP 2 をやり直す（変えた部分だけが作り直される）

## STEP 5: 公開（`/sc-upload` の STEP 3.7 で行う）

**公開の仕組み（ユーザー決定 2026-10-23）:** 学習版は、SC の本編が公開されたあとの `/sc-upload` の中で、**同じ EP 番号**の回を
「アップロード（即時公開）→ ショートの関連動画（Chrome）→ コメント返信（日本語）」まで一気に行う。常駐のジョブは使わない。
`/sc-upload` は SC の関連動画の設定（STEP 3.5）と同じタイミングで、公開済みの SC の回に対応する学習版を拾う。

**この `/sc-learn` の終わりに、次をする:**
1. ユーザーが動画・サムネイル・ショートを確認して **OK を出した**ら、公開 OK を記録する（OK がなければ、記録しない＝公開されない）:
   ```bash
   cd learning && python3 learn_targets.py --approve ep106
   ```
2. 内容だけ確認したいときは（通信しない）: `cd learning && python3 learn_upload.py ep106 --dry-run`
3. 初回の認証と Google Cloud の準備は `learning/YOUTUBE_SETUP.md`。

**関連動画は API では設定できない**（Studio のパソコン版のみ。同じチャンネルの動画にしか設定できない）ので、Chrome で行う。
ショートの説明欄の URL は、クリックできないことがあるので、本編への誘導は関連動画で行う。

確認用に、非公開でアップロードして Studio で見ることもできる（公開 OK は不要）: `cd learning && python3 learn_upload.py ep106`
動画 ID は `learning/uploads/ep{NNN}.json` に残る。

## 参考: ファイルの役割

| ファイル | 役割 |
|---|---|
| `learning/lessons/ep{NNN}.json` | 台本 |
| `learning/build_lesson.py` | 日本語音声の生成、英文の切り出し、並べて1本にする（動画用の timeline.json も出す） |
| `learning/build_video.py` | シーン画像に英文と日本語訳の字幕を載せて、動画にする（冒頭に Tokio を登場させ、英単語をハイライト） |
| `learning/learn_upload.py` | 学習版チャンネルへのアップロード（本編・サムネイル・ショート） |
| `learning/learn_targets.py` | 公開 OK の記録、公開・関連動画の対象の洗い出し |
| `learning/learn_comment_reply.py` | 学習版チャンネルの未返信コメントの取得・日本語での返信 |
| `learning/words.py` | 英語の各文の単語ごとの時刻を、手元の Whisper で取る（台本の単語に当てはめる） |
| `learning/tts_ja.py` | 日本語の音声生成（Tokio の声。PCM にそろえて保存） |
| `learning/clips.py` | 本編の音声から、1文ずつ切り出す（書き起こしで照合） |
| `learning/audio_check.py` | 日本語の読み確認、音声の書き起こし |
| `learning/chime.wav` | 日本語の訳の前に鳴らす合図の音 |
