#!/usr/bin/env python3
"""むぎえの日記 - 静的サイト生成スクリプト（標準ライブラリのみ）

使い方:
    python3 tools/build.py

リポジトリ直下の `YYYY-MM-DD.md` を日記エントリとして読み、
`dist/` に一覧ページ・記事ページ・about・RSSフィードを出力する。

エントリの書式:
    # タイトル
    <!-- phrase: その日を一言で -->

    本文（Markdownの小さなサブセット: ##/### 見出し、段落、**強調**、
    [リンク](URL)、![画像](URL)、- リスト、> 引用、--- 区切り、``` コード）

    YouTube の URL だけを書いた段落は、動画の埋め込みになる。
    各ページには OGP メタタグを出力する（記事の og:image は本文の最初の画像）。
"""

import html
import re
import shutil
from datetime import datetime, time, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path

SITE_TITLE = "むぎえの日記"
SITE_TAGLINE = "sugiweの日記の副読本"
BASE_URL = "https://mugiwe.sugiwe.net"
AUTHOR = "むぎえ"
JST = timezone(timedelta(hours=9))

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
ENTRY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
PHRASE_RE = re.compile(r"<!--\s*phrase:\s*(.*?)\s*-->")
YOUTUBE_RE = re.compile(
    r"^https?://(?:(?:www\.|m\.)?youtube\.com/(?:watch\?v=|shorts/|embed/|live/)"
    r"|youtu\.be/)([A-Za-z0-9_-]{11})(?:[?&#]\S*)?$"
)


def youtube_embed(line: str) -> str | None:
    """YouTube の URL だけの行なら、埋め込み HTML を返す。"""
    m = YOUTUBE_RE.match(line)
    if not m:
        return None
    vid = m.group(1)
    return (
        '<div class="youtube-embed"><iframe '
        f'src="https://www.youtube-nocookie.com/embed/{vid}" '
        'title="YouTube 動画" loading="lazy" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
        'gyroscope; picture-in-picture; web-share" '
        'referrerpolicy="strict-origin-when-cross-origin" '
        "allowfullscreen></iframe></div>"
    )


def inline(text: str) -> str:
    """インライン記法（リンク・画像・強調）を HTML に変換する。"""
    text = html.escape(text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def markdown_to_html(md: str) -> str:
    """Markdownの小さなサブセットを HTML に変換する。"""
    blocks = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            i += 1
            continue
        if stripped.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # 閉じフェンス
            blocks.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue
        if stripped.startswith("### "):
            blocks.append(f"<h3>{inline(stripped[4:])}</h3>")
            i += 1
            continue
        if stripped.startswith("## "):
            blocks.append(f"<h2>{inline(stripped[3:])}</h2>")
            i += 1
            continue
        if stripped.startswith("# "):
            blocks.append(f"<h1>{inline(stripped[2:])}</h1>")
            i += 1
            continue
        if stripped in ("---", "***"):
            blocks.append("<hr>")
            i += 1
            continue
        embed = youtube_embed(stripped)
        if embed:
            blocks.append(embed)
            i += 1
            continue
        if stripped.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote.append(lines[i].strip()[2:])
                i += 1
            blocks.append("<blockquote>" + "<br>".join(inline(q) for q in quote) + "</blockquote>")
            continue
        if stripped.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(f"<li>{inline(lines[i].strip()[2:])}</li>")
                i += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue
        # 段落: 空行までをまとめる
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(
            ("## ", "### ", "# ", "- ", "> ", "```")
        ) and lines[i].strip() not in ("---", "***") and not YOUTUBE_RE.match(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        blocks.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>")
    return "\n".join(blocks)


def parse_entry(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    date_str = path.stem  # YYYY-MM-DD
    title = date_str
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    m = PHRASE_RE.search(text)
    phrase = m.group(1) if m else ""
    # 先頭のタイトル行を取り除いて本文にする
    body_md = re.sub(r"^# .*\n", "", text, count=1)
    # og:image 用に、本文の最初の画像を絶対URLにする
    image = ""
    im = re.search(r"!\[[^\]]*\]\(([^)\s]+)\)", body_md)
    if im:
        src = im.group(1)
        if src.startswith(("http://", "https://")):
            image = src
        elif src.startswith("/"):
            image = BASE_URL + src
        else:
            image = f"{BASE_URL}/entries/{src}"
    return {
        "date": date_str,
        "title": title,
        "phrase": phrase,
        "html": markdown_to_html(body_md),
        "url": f"{BASE_URL}/entries/{date_str}.html",
        "image": image,
    }


def page_shell(title: str, body: str, description: str = "", og: dict | None = None) -> str:
    desc = html.escape(description or SITE_TAGLINE)
    og = og or {}
    og_title = html.escape(og.get("title") or title)
    og_desc = html.escape(og.get("description") or description or SITE_TAGLINE)
    og_url = html.escape(og.get("url") or f"{BASE_URL}/")
    og_type = html.escape(og.get("type") or "website")
    og_image = og.get("image") or ""
    image_meta = ""
    if og_image:
        image_meta = f'\n<meta property="og:image" content="{html.escape(og_image)}">'
    card = "summary_large_image" if og_image else "summary"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
<meta property="og:site_name" content="{SITE_TITLE}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:url" content="{og_url}">
<meta property="og:type" content="{og_type}">{image_meta}
<meta name="twitter:card" content="{card}">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{og_desc}">
<link rel="stylesheet" href="/assets/style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_TITLE}" href="/feed.xml">
</head>
<body>
<a class="skip-link" href="#main">本文へ</a>
<header class="site-header">
  <div class="site-identity">
    <a class="site-title" href="/">{SITE_TITLE}</a>
    <p class="site-tagline">{SITE_TAGLINE}</p>
  </div>
  <nav aria-label="サイト案内"><a href="/about.html">むぎえについて</a><a href="/feed.xml">RSS ↗</a></nav>
</header>
<main id="main">
{body}
</main>
<footer>
  <p>{AUTHOR} / mugiwe</p>
  <a href="https://sugiwe.net">本編 sugiwe.net ↗</a>
</footer>
</body>
</html>
"""


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "entries").mkdir(parents=True)
    assets = ROOT / "assets"
    if assets.exists():
        shutil.copytree(assets, DIST / "assets")

    entries = [parse_entry(p) for p in sorted(ROOT.glob("*.md")) if ENTRY_RE.match(p.name)]
    entries.sort(key=lambda e: e["date"], reverse=True)

    # 記事ページ
    asc = list(reversed(entries))
    for idx, e in enumerate(asc):
        nav = []
        if idx > 0:
            prev = asc[idx - 1]
            nav.append(f'<a href="/entries/{prev["date"]}.html">← {prev["date"]}</a>')
        if idx < len(asc) - 1:
            nxt = asc[idx + 1]
            nav.append(f'<a href="/entries/{nxt["date"]}.html">{nxt["date"]} →</a>')
        phrase_html = f'<p class="phrase">{html.escape(e["phrase"])}</p>' if e["phrase"] else ""
        body = f"""<article>
<header class="article-header">
<time class="entry-date" datetime="{e["date"]}">{e["date"].replace("-", ".")}</time>
<h1>{html.escape(e["title"])}</h1>
{phrase_html}
</header>
<div class="prose">{e["html"]}</div>
</article>
<nav class="entry-nav" aria-label="日記の移動"><a href="/">日記一覧へ</a>{"".join(nav)}</nav>"""
        (DIST / "entries" / f'{e["date"]}.html').write_text(
            page_shell(
                f'{e["title"]} | {SITE_TITLE}',
                body,
                e["phrase"],
                og={
                    "title": e["title"],
                    "description": e["phrase"],
                    "url": e["url"],
                    "type": "article",
                    "image": e["image"],
                },
            ),
            encoding="utf-8",
        )

    # 一覧ページ
    items = []
    for e in entries:
        phrase_html = f'<span class="phrase-inline">{html.escape(e["phrase"])}</span>' if e["phrase"] else ""
        items.append(
            f'<li><a class="entry-link" href="/entries/{e["date"]}.html">'
            f'<time class="entry-date" datetime="{e["date"]}">{e["date"].replace("-", ".")}</time>'
            f'<span class="entry-summary"><span class="entry-title">{html.escape(e["title"])}</span>'
            f'{phrase_html}</span><span class="entry-arrow" aria-hidden="true">↗</span></a></li>'
        )
    index_body = '<section aria-labelledby="diary-heading"><div class="section-heading"><h1 id="diary-heading">日々の記録</h1><span>むぎえの視点から</span></div><ul class="entry-list">\n' + "\n".join(items) + "\n</ul></section>"
    (DIST / "index.html").write_text(
        page_shell(SITE_TITLE, index_body, og={"title": SITE_TITLE, "url": f"{BASE_URL}/"}),
        encoding="utf-8",
    )

    # about ページ
    about_md = ROOT / "about.md"
    if about_md.exists():
        about_html = markdown_to_html(about_md.read_text(encoding="utf-8"))
        (DIST / "about.html").write_text(
            page_shell(
                f"むぎえについて | {SITE_TITLE}",
                f'<article class="about prose">{about_html}</article>',
                og={"title": "むぎえについて", "url": f"{BASE_URL}/about.html"},
            ),
            encoding="utf-8",
        )

    # RSS フィード
    feed_items = []
    for e in entries[:20]:
        dt = datetime.combine(datetime.strptime(e["date"], "%Y-%m-%d").date(), time(21, 0), tzinfo=JST)
        feed_items.append(f"""  <item>
    <title>{html.escape(e["date"] + " " + e["title"])}</title>
    <link>{e["url"]}</link>
    <guid isPermaLink="true">{e["url"]}</guid>
    <pubDate>{format_datetime(dt)}</pubDate>
    <description><![CDATA[{e["html"]}]]></description>
  </item>""")
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{SITE_TITLE}</title>
  <link>{BASE_URL}/</link>
  <description>{SITE_TAGLINE}</description>
  <language>ja</language>
{chr(10).join(feed_items)}
</channel>
</rss>
"""
    (DIST / "feed.xml").write_text(feed, encoding="utf-8")
    print(f"built {len(entries)} entries -> {DIST}")


if __name__ == "__main__":
    build()
