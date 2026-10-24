# 引き継ぎ: Vercel の Deployment Storage 対策（2026-10-25）

## 経緯
- 2026-10-25 07:57、Vercel から「無料チーム narunakajimas-projects の Deployment Storage が無料枠（10GB）の75%に達した。100%で再度通知」というメールが届いた
- 原因: kagaku-life と samurai-chronicles に `.vercelignore` がなく、main に push するたびにリポジトリ全体が1回分のデプロイとして保存されていた。KL は1回あたり約104MB（大半はサイトで使わない `assets/cast` 82MB と `assets/cards`）。夜間ニュース採点の push もあり、1日1〜3回デプロイされていた。SC は1回あたり約29MB
- 有料プラン（Pro）は不要と判断した

## 済んだこと（クラウドセッション）
- 両リポジトリに `.vercelignore` を追加し、main に push した（KL `aae72b1`、SC `79dfc3f`）
  - 方式は許可リスト: `/*` で全部除外し、サイトで使うファイルだけを `!` で戻す
  - KL: index.html, episodes.html, playlists.html, vercel.json, LOGO.PNG, cast_daisuke.png, cast_saori.png
  - SC: index.html, episodes.html, playlists.html, vercel.json, LOGO.PNG
  - 動画のサムネイルは img.youtube.com から読むので、リポジトリには要らない
  - 1回のデプロイは KL 約1MB、SC 約2MB になる見込み
- 公開中のサイトはまだ確かめていない（クラウドからは接続できなかった）

## iMac でやること
1. **公開中のサイトを確認する**: kagaku-life.com と SC のサイトを Chrome で開き、ロゴ、KL の二人の立ち絵（cast_*.png）、動画一覧（/episodes）、再生リスト（/playlists）が表示されるか見る。欠けているファイルがあれば、両リポジトリの `.vercelignore` の許可リストに追加して push する
2. **古いデプロイを消す**（Chrome で Vercel の管理画面を操作。`.vercelignore` だけでは今ある分は減らない）
   - vercel.com → narunakajimas-projects → KL のプロジェクト → Settings → Security → Deployment Retention Policy で保持期間を短くする（例: 30日）。期限を過ぎた古いデプロイが自動で消え、公開中の最新デプロイは残る
   - すぐに空けたいときは、Deployments の一覧で古いデプロイを削除する（Production の最新、つまり Current は消さない）
   - SC のプロジェクトでも同じことをする。チームに lamp-whisper のプロジェクトがあれば、それも確認する（lamp-whisper も `.vercelignore` がないが、リポジトリは約3MBで影響は小さい）
   - 作業後、Usage 画面で Deployment Storage が下がったか確かめる（反映に時間がかかる場合がある）
3. この作業が終わったら、このメモ（`HANDOFF_vercel_storage_2026-10-25.md`）は削除してよい

## 注意
- 今後、サイトに新しいファイル（画像・CSS・JSON など）を足すときは `.vercelignore` の許可リストへの追加が必要（追加しないと本番に載らない）。ファイルの冒頭にも書いてある
