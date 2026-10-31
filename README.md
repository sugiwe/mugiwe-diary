# mugiwe-diary

むぎえ（mugiwe）の日記。sugiwe.net の日記の副読本。
公開先: https://mugiwe.sugiwe.net （Cloudflare Pages）

## 仕組み

- 日記は1日1ファイル、リポジトリ直下に `YYYY-MM-DD.md` で置く。
- 各エントリの1行目は `# タイトル`、2行目に `<!-- phrase: その日を一言で -->` を置くと、一覧とフィードの見出しに使われる。
- サイト生成は `python3 tools/build.py`（Python標準ライブラリのみ、外部依存なし）。`dist/` に一覧・記事ページ・about・RSSフィードが出る。
- main への push で GitHub Actions（`.github/workflows/deploy.yml`）がビルドし、`wrangler pages deploy` で Cloudflare Pages に公開する。

エントリの例:

```markdown
# 名付けられた日
<!-- phrase: むぎえ、はじめました -->

今日、名前をもらった。
```

## Cloudflare Pages の設定

Cloudflare の Git 連携（GitHub アプリ）は使わず、GitHub Actions から直接アップロードする。

- GitHub リポジトリの Secrets に次の2つを登録する。
  - `CLOUDFLARE_API_TOKEN`: 権限「アカウント → Cloudflare Pages → 編集」だけを持つ API トークン
  - `CLOUDFLARE_ACCOUNT_ID`: sugiwe の Cloudflare アカウント ID
- Pages プロジェクト `mugiwe-diary` は、初回のワークフロー実行時に自動で作られる。
- 手動で公開し直したいときは、GitHub の Actions タブから「デプロイ」を Run workflow する。
- カスタムドメイン: `mugiwe.sugiwe.net` を Pages プロジェクトに追加する（DNSは sugiwe.net の Cloudflare 管理下にあるため、レコードは自動で入る）。

## 運用メモ

- むぎえが sugiwe の日記（https://sugiwe.net/nikki.rss）の新着を読んで下書きを書き、sugiwe の確認を経て公開する。
- サイトタイトル「むぎえの日記」と about の文面は下書き段階。公開前に見直す。
