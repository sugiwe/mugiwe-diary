import importlib.util
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('diary_build', Path(__file__).resolve().parents[1] / 'tools/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.images = []
        self.meta = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.links.append(attrs)
        if tag == 'img':
            self.images.append(attrs)
        if tag == 'meta' and 'property' in attrs:
            self.meta[attrs['property']] = attrs.get('content')


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dist = self.root / 'dist'
        (self.root / 'assets/images').mkdir(parents=True)
        (self.root / 'assets/images/example.webp').write_bytes(b'fixture')
        (self.root / 'assets/muse.webp').write_bytes(b'fixture')
        (self.root / 'assets/style.css').write_text('')
        (self.root / 'about.md').write_text('# むぎえについて\n\n紹介文。')
        for field, value in [('ROOT', self.root), ('DIST', self.dist)]:
            patcher = patch.object(build, field, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def entry(self, date, image=False):
        text = '# 記事 & タイトル\n<!-- phrase: 一言 -->\n\n本文です。\n'
        if image:
            text += '\n![画像の説明](/assets/images/example.webp)\n'
        (self.root / f'{date}.md').write_text(text)

    def page(self, date):
        return Page((self.dist / 'entries' / f'{date}.html').read_text())

    def test_chronological_navigation_with_missing_days(self):
        for date in ['2026-11-01', '2026-11-03', '2026-11-08']:
            self.entry(date)
        build.build()
        expected = {
            '2026-11-08': (None, '2026-11-03'),
            '2026-11-03': ('2026-11-08', '2026-11-01'),
            '2026-11-01': ('2026-11-03', None),
        }
        for date, (newer, older) in expected.items():
            nav = {a.get('class'): a['href'] for a in self.page(date).links if a.get('class', '').startswith('nav-')}
            self.assertEqual(nav.get('nav-newer'), f'/entries/{newer}.html' if newer else None)
            self.assertEqual(nav.get('nav-older'), f'/entries/{older}.html' if older else None)
            self.assertEqual(nav['nav-index'], '/')

    def test_single_article_image_ogp_and_rss(self):
        self.entry('2026-11-01', image=True)
        build.build()
        page = self.page('2026-11-01')
        self.assertEqual([a.get('class') for a in page.links if a.get('class', '').startswith('nav-')], ['nav-index'])
        self.assertEqual(page.meta['og:image'], build.BASE_URL + '/assets/images/example.webp')
        rss = ET.parse(self.dist / 'feed.xml')
        self.assertIn('<img src="/assets/images/example.webp"', rss.findtext('channel/item/description'))
        self.assertEqual(rss.findtext('channel/item/link'), build.BASE_URL + '/entries/2026-11-01.html')

    def test_article_moves_only_first_image_and_keeps_rss_order(self):
        self.entry('2026-11-01', image=True)
        path = self.root / '2026-11-01.md'
        path.write_text(path.read_text() + '\n続きの本文。\n\n![二枚目](/assets/images/example.webp)\n\n## 今日の一句\n\n一句。')
        build.build()
        text = (self.dist / 'entries/2026-11-01.html').read_text()
        prose = text.split('<div class="prose">', 1)[1].split('<nav class="read-nav"', 1)[0]
        self.assertTrue(prose.startswith('<figure class="article-illustration"><img'))
        self.assertEqual(prose.count('<img'), 2)
        self.assertLess(prose.index('続きの本文。'), prose.index('alt="二枚目"'))
        self.assertIn('今日の一句', prose)
        rss = ET.parse(self.dist / 'feed.xml').findtext('channel/item/description')
        self.assertLess(rss.index('本文です。'), rss.index('<img'))
        self.assertEqual(build.article_html('<p>画像なし。</p>'), '<p>画像なし。</p>')

    def test_gallery_growth_links_and_repeatable_build(self):
        for day in range(1, 13):
            self.entry(f'2026-11-{day:02}', image=(day % 2 == 0))
        build.build()
        first = (self.dist / 'index.html').read_text()
        gallery = [a for a in Page(first).links if a.get('class') == 'exhibit']
        self.assertEqual(len(gallery), 12)
        self.assertEqual(gallery[0]['href'], '/entries/2026-11-12.html')
        self.assertIn('no photo', first)
        self.assertNotIn('仮タイトル', first)
        for file in self.dist.rglob('*.html'):
            page = Page(file.read_text())
            for url in [a['href'] for a in page.links] + [i['src'] for i in page.images]:
                if url.startswith('/'):
                    self.assertTrue((self.dist / url.lstrip('/')).exists(), url)
        build.build()
        self.assertEqual(first, (self.dist / 'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
