"""Main pages and their CSS dependency graph must be served without a CDN."""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and set(attrs.get('rel', '').split()) & {'stylesheet', 'icon', 'manifest'}:
            self.urls.append(attrs.get('href', ''))
        elif tag in {'script', 'img', 'source', 'audio', 'video'} and attrs.get('src'):
            self.urls.append(attrs['src'])
        if attrs.get('srcset'):
            self.urls.extend(item.strip().split()[0] for item in attrs['srcset'].split(','))


class LocalStaticTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='local-assets')

    def check_asset(self, url, seen):
        if url.startswith(('data:', 'blob:')):
            return
        parsed = urlsplit(url)
        self.assertFalse(parsed.netloc, f'External asset: {url}')
        self.assertFalse(parsed.scheme, f'External asset: {url}')
        self.assertTrue(parsed.path.startswith(settings.STATIC_URL), url)
        name = unquote(parsed.path.removeprefix(settings.STATIC_URL))
        path = finders.find(name)
        self.assertIsNotNone(path, f'Missing local asset: {url}')
        if name in seen:
            return
        seen.add(name)
        if name.endswith('.css'):
            css = re.sub(r'/\*.*?\*/', '', Path(path).read_text(encoding='utf-8'), flags=re.S)
            references = re.findall(r'url\(\s*(?:"([^"]*)"|\'([^\']*)\'|([^)]*))\s*\)', css)
            for reference in references:
                target = next(value for value in reference if value).strip()
                self.check_asset(urljoin(url, target), seen)
            for target in re.findall(r'@import\s+["\']([^"\']+)', css):
                self.check_asset(urljoin(url, target), seen)

    def test_main_pages_load_only_resolvable_local_assets_including_nested_fonts(self):
        for authenticated in (False, True):
            if authenticated:
                self.client.force_login(self.user)
            pages = ['home', 'about']
            if authenticated:
                pages += ['profile', 'edit_settings', 'by_date']
            else:
                pages += ['entry']
            for page in pages:
                with self.subTest(authenticated=authenticated, page=page):
                    response = self.client.get(reverse(page, args=['2026-10'] if page == 'by_date' else []),
                                               HTTP_HOST='testserver')
                    self.assertEqual(response.status_code, 200)
                    parser = AssetParser()
                    parser.feed(response.content.decode())
                    seen = set()
                    for url in parser.urls:
                        self.check_asset(url, seen)
                    self.assertTrue(any(name.endswith('.woff2') for name in seen))

    def test_secondary_font_stylesheets_and_all_icon_shims_resolve_locally(self):
        for name in ('hwyd/css/style.css', 'general_app/css/font.css',
                     'hwyd/vendor/font-awesome/7.3.1/css/v4-shims.min.css',
                     'hwyd/vendor/font-awesome/7.3.1/css/v4-font-face.min.css',
                     'hwyd/vendor/font-awesome/7.3.1/css/v5-font-face.min.css'):
            with self.subTest(asset=name):
                self.check_asset(settings.STATIC_URL + name, set())
