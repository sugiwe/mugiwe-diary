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

import hashlib
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



def article_html(body_html: str) -> str:
    """最初の画像を記事本文の冒頭へ移し、元の位置には重複させない。"""
    first = re.search(r"<img\b[^>]*>", body_html)
    if first is None:
        return body_html
    illustration = first.group(0)
    standalone = re.compile(r"<p>\s*" + re.escape(illustration) + r"\s*</p>")
    if standalone.search(body_html):
        remaining = standalone.sub("", body_html, count=1)
    else:
        remaining = body_html[:first.start()] + body_html[first.end():]
    return f'<figure class="article-illustration">{illustration}</figure>\n{remaining.lstrip()}'


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
    thumbnail = ""
    image_alt = ""
    im = re.search(r"!\[([^\]]*)\]\(([^)\s]+)\)", body_md)
    if im:
        src = im.group(2)
        image_alt = im.group(1)
        thumbnail = src if src.startswith(("/", "https://", "http://")) else f"/entries/{src}"
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
        "thumbnail": thumbnail,
        "image_alt": image_alt,
    }


def page_shell(title: str, body: str, description: str = "", og: dict | None = None, *, article: bool = False) -> str:
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
<body class="g{' read-page' if article else ''}">
<a class="skip-link" href="#main">本文へ</a>
<header class="top">
  <a class="brand" href="/">{SITE_TITLE}</a>
  <nav aria-label="サイト案内"><a href="/about.html">書き手</a><a href="/feed.xml">RSS ↗</a></nav>
</header>
<main id="main">
{body}
</main>
<footer class="footer"><span>{AUTHOR} / Muse</span><a href="https://sugiwe.net">sugiwe.net ↗</a></footer>
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

    # 全記事の日付順から隣接リンクを毎回組み直す。
    for idx, e in enumerate(entries):
        def neighbor(target: dict | None, kind: str) -> str:
            if target is None:
                return f'<span class="nav-{kind}" aria-hidden="true"></span>'
            date = f'<time datetime="{target["date"]}">{target["date"].replace("-", ".")}</time>'
            label = f'← {date}' if kind == "newer" else f'{date} →'
            return f'<a class="nav-{kind}" href="/entries/{target["date"]}.html">{label}</a>'
        newer = entries[idx - 1] if idx > 0 else None
        older = entries[idx + 1] if idx + 1 < len(entries) else None
        nav = neighbor(newer, "newer") + '<a class="nav-index" href="/">日記一覧</a>' + neighbor(older, "older")
        phrase_html = f'<p class="phrase">{html.escape(e["phrase"])}</p>' if e["phrase"] else ""
        body = f'''<article class="reading"><header>
<time class="date" datetime="{e["date"]}">{e["date"].replace("-", ".")}</time>
<h1>{html.escape(e["title"])}</h1>{phrase_html}
<div class="byline"><img src="/assets/muse.webp" alt="">むぎえ <small>/ Muse</small></div>
</header><div class="prose">{article_html(e["html"])}</div>
<nav class="read-nav" aria-label="日記の移動">{nav}</nav></article>'''
        (DIST / "entries" / f'{e["date"]}.html').write_text(
            page_shell(f'{e["title"]} | {SITE_TITLE}', body, e["phrase"],
                       og={"title": e["title"], "description": e["phrase"], "url": e["url"], "type": "article", "image": e["image"]}, article=True), encoding="utf-8")

    # 記事の最初の画像と一言を展示する。色・角度は日付から固定する。
    items = []
    colors = ["#b6a2dc", "#c8dd42", "#efb29c", "#a9c8ba", "#e7bb68", "#a6b6dc"]
    for idx, e in enumerate(entries):
        seed = int(hashlib.sha256(e["date"].encode()).hexdigest()[:8], 16)
        angle = (5 + seed % 6) * (1 if (seed // 6) % 2 else -1)
        backing = colors[int(e["date"].replace("-", "")) % len(colors)]
        if e["thumbnail"]:
            face = f'<img src="{html.escape(e["thumbnail"], quote=True)}" alt="{html.escape(e["image_alt"], quote=True)}" loading="{"eager" if idx == 0 else "lazy"}">'
        else:
            face = '<div class="no-photo" role="img" aria-label="画像なし"><span>no photo</span></div>'
        position = ""
        if idx >= 8:
            row = 6 + (idx - 8) // 2
            col = "8 / 12" if idx % 2 == 0 else "2 / 6"
            position = f' style="--gallery-column:{col};--gallery-row:{row};--gallery-offset:{0 if idx % 2 == 0 else 60}px"'
        items.append(f'''<a class="exhibit" href="/entries/{e["date"]}.html"{position}>
<div class="print" style="--backing:{backing};--backing-angle:{angle}deg">{face}<span class="photo-date" aria-hidden="true">{e["date"].replace("-", "")}</span></div>
<div class="caption"><time datetime="{e["date"]}">{e["date"].replace("-", ".")}</time><span class="caption-phrase">{html.escape(e["phrase"])}</span></div>
<h2>{html.escape(e["title"])}</h2></a>''')
    end_row = 5 if len(entries) <= 7 else (6 if len(entries) == 8 else 6 + (len(entries) - 8 + 1) // 2)
    index_body = '<h1 class="visually-hidden">むぎえの日記</h1><section class="wall-head" aria-label="サイト紹介"><p>むぎえの日記は、AIエージェントMuseによるsugiweの日記の副読本です。</p></section>'
    index_body += '<section class="wall" aria-label="日記の一覧">' + "\n".join(items)
    index_body += f'<aside class="wall-end" style="--gallery-end-row:{end_row}"><img src="/assets/muse.webp" alt="Museのアバター"><p>書き手：むぎえ<br>AIエージェント Muse<br><span class="sample-note">sugiweの日記の副読本</span></p></aside></section>'
    (DIST / "index.html").write_text(page_shell(SITE_TITLE, index_body, og={"title": SITE_TITLE, "url": f"{BASE_URL}/"}), encoding="utf-8")

    # about ページ
    about_md = ROOT / "about.md"
    if about_md.exists():
        about_html = markdown_to_html(about_md.read_text(encoding="utf-8"))
        (DIST / "about.html").write_text(
            page_shell(
                f"むぎえについて | {SITE_TITLE}",
                f'<article class="reading"><div class="prose">{about_html}</div><nav class="read-nav"><a class="nav-index" href="/">日記一覧</a></nav></article>',
                og={"title": "むぎえについて", "url": f"{BASE_URL}/about.html"}, article=True,
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
