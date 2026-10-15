"""Public indexing and canonical HTTP behavior without private data in search."""
import re
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .seo import PUBLIC_PAGE_NAMES
from .test_public_pages import PageElements


class PublicSEOTests(TestCase):
    def test_sitemap_contains_only_public_canonical_200_pages_without_fake_lastmod(self):
        response = self.client.get('/sitemap.xml?ignored=1', HTTP_HOST='testserver')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml; charset=utf-8')
        root = ElementTree.fromstring(response.content)
        namespace = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        self.assertEqual(root.tag, namespace + 'urlset')
        locations = [item.text for item in root.findall(namespace + 'url/' + namespace + 'loc')]
        expected = ['https://productivum.ru' + reverse(name) for name in PUBLIC_PAGE_NAMES]
        self.assertEqual(locations, expected)
        self.assertEqual(len(locations), len(set(locations)))
        self.assertFalse(root.findall('.//' + namespace + 'lastmod'))
        for location in locations:
            self.assertEqual(urlsplit(location).scheme, 'https')
            self.assertFalse(urlsplit(location).query)
            page = self.client.get(urlsplit(location).path)
            self.assertEqual(page.status_code, 200)
            canonical = [link['href'] for link in PageElements(page).tags('link') if link.get('rel') == 'canonical']
            self.assertEqual(canonical, [location])
        for excluded in ('entry', 'profile', 'index', 'edit_settings', 'activity_users'):
            self.assertNotIn('https://productivum.ru' + reverse(excluded), locations)

    def test_robots_allows_auth_and_public_resources_and_links_https_sitemap(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        robot = RobotFileParser()
        robot.parse(response.content.decode().splitlines())
        self.assertEqual(robot.site_maps(), ['https://productivum.ru/sitemap.xml'])
        for path in ('/', '/home/entry/?type=register&next=/habitus/', '/static/general_app/css/public.css',
                     '/static/general_app/js/home-preview.js', '/guides/habitus/'):
            for bot in ('Googlebot', 'YandexBot'):
                self.assertTrue(robot.can_fetch(bot, path))
        self.assertEqual(self.client.head('/robots.txt').status_code, 200)
        self.assertEqual(self.client.head('/sitemap.xml').content, b'')

    def test_login_and_registration_noindex_for_every_query_and_validation_error(self):
        for query in ('', '?type=login', '?type=register&next=%2Fhabitus%2F%23settings',
                      '?type=unexpected&next=https%3A%2F%2Fevil.example%2F'):
            response = self.client.get(reverse('entry') + query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Robots-Tag'], 'noindex, follow')
            self.assertContains(response, '<meta name="robots" content="noindex, follow">', html=True)
            self.assertFalse([link for link in PageElements(response).tags('link') if link.get('rel') == 'canonical'])
        invalid = self.client.post(reverse('entry'), {'login': '', 'username': 'missing', 'password': 'bad'})
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid['X-Robots-Tag'], 'noindex, follow')
        user = get_user_model().objects.create_user('seo-logged-in')
        self.client.force_login(user)
        response = self.client.get(reverse('entry') + '?type=register')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['X-Robots-Tag'], 'noindex, follow')

    def test_public_content_has_unique_server_metadata_one_h1_and_no_noindex(self):
        titles, descriptions = [], []
        for name in PUBLIC_PAGE_NAMES:
            response = self.client.get(reverse(name), {'utm_source': 'test', 'next': '/habitus/'})
            self.assertEqual(response.status_code, 200)
            elements = PageElements(response)
            self.assertEqual(len(elements.tags('h1')), 1)
            self.assertEqual(len(elements.tags('main')), 1)
            self.assertNotIn('noindex', response.get('X-Robots-Tag', ''))
            self.assertFalse([meta for meta in elements.tags('meta') if meta.get('name') == 'robots' and 'noindex' in meta.get('content', '')])
            title = re.findall(r'<title>(.*?)</title>', response.content.decode(), re.S)
            self.assertEqual(len(title), 1)
            titles += title
            description = [meta['content'] for meta in elements.tags('meta') if meta.get('name') == 'description']
            self.assertEqual(len(description), 1)
            self.assertTrue(description[0].strip())
            descriptions += description
        self.assertEqual(len(set(titles)), len(PUBLIC_PAGE_NAMES))
        self.assertEqual(len(set(descriptions)), len(PUBLIC_PAGE_NAMES))
        home = self.client.get('/')
        self.assertContains(home, '<title>Трекер привычек онлайн — Habitus | Productivum</title>', html=True)
        self.assertContains(home, '<h1 id="home-title">Habitus — онлайн-трекер привычек</h1>', html=True)
        about = self.client.get(reverse('about'))
        self.assertContains(about, 'О проекте Habitus и его авторе')
        self.assertContains(about, 'Дмитрий')
        self.assertContains(about, 'Ярославле')
        self.assertContains(about, 'exp-1c">')
        self.assertNotContains(about, 'calculateYearsMonths')
        self.assertEqual(len(PageElements(about).tags('h2')), 3)

    def test_guides_are_public_interlinked_and_fully_rendered_without_login(self):
        for name in ('habitus_guide', 'habit_tracking_guide'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'привыч')
            self.assertContains(response, 'месяц')
            for linked in PUBLIC_PAGE_NAMES:
                self.assertContains(response, f'href="{reverse(linked)}')
            self.assertNotContains(response, 'PENDING_GUIDES')
            self.assertNotContains(response, 'data-activity-id')

    def test_content_only_pages_skip_unused_framework_css_but_keep_needed_fonts(self):
        for name in ('home', 'about', 'habitus_guide', 'habit_tracking_guide'):
            response = self.client.get(reverse(name))
            self.assertNotContains(response, 'bootstrap.min.css')
            self.assertContains(response, 'font-awesome/')
            preloads = [tag for tag in PageElements(response).tags('link') if tag.get('rel') == 'preload' and 'google-fonts/files/' in tag.get('href', '')]
            self.assertEqual(len(preloads), 2)
            self.assertTrue(all(tag.get('as') == 'font' and 'crossorigin' in tag for tag in preloads))
        self.assertContains(self.client.get(reverse('entry')), 'bootstrap.min.css')

    def test_public_internal_links_and_section_anchors_resolve(self):
        for name in PUBLIC_PAGE_NAMES:
            response = self.client.get(reverse(name))
            elements = PageElements(response)
            ids = {attrs['id'] for _, attrs in elements.elements if 'id' in attrs}
            for link in elements.tags('a'):
                href = link.get('href', '')
                if href.startswith('#') and len(href) > 1:
                    self.assertIn(href[1:], ids)
                elif href.startswith('/'):
                    parts = urlsplit(href)
                    linked = self.client.get(parts.path + ('?' + parts.query if parts.query else ''), HTTP_HOST='testserver')
                    self.assertIn(linked.status_code, (200, 302), href)
                    if linked.status_code == 302:
                        self.assertTrue(linked['Location'].startswith(reverse('entry')), href)
                    elif parts.fragment:
                        target_ids = {attrs['id'] for _, attrs in PageElements(linked).elements if 'id' in attrs}
                        self.assertIn(parts.fragment, target_ids)

    @override_settings(DEBUG=False)
    def test_private_pages_remain_protected_and_missing_page_is_a_real_404(self):
        for name in ('profile', 'index', 'activity_users'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response['Location'].startswith(reverse('entry')))
        response = self.client.get('/missing-seo-regression/')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('Location', response)
        self.assertNotContains(response, 'rel="canonical"', status_code=404)


@override_settings(CANONICAL_REDIRECTS_ENABLED=True, PUBLIC_SITE_ORIGIN='https://productivum.ru',
                   ALLOWED_HOSTS=['productivum.ru', 'www.productivum.ru'],
                   SECURE_PROXY_SSL_HEADER=None, USE_X_FORWARDED_HOST=False, DEBUG=False)
class CanonicalRedirectTests(TestCase):
    def test_http_and_www_preserve_path_and_raw_query_in_one_permanent_redirect(self):
        query = 'tag=a%2Fb&tag=b&next=%2Fhabitus%2F%23settings'
        for host, secure in (('productivum.ru', False), ('www.productivum.ru', False), ('www.productivum.ru', True)):
            for path in ('/', '/guides/habitus/', '/habitus/2026-10', '/missing-seo-regression/'):
                response = self.client.get(path + '?' + query, HTTP_HOST=host, secure=secure)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response['Location'], 'https://productivum.ru' + path + '?' + query)

    def test_every_home_alias_reaches_canonical_root_without_an_extra_hop(self):
        for host in ('productivum.ru', 'www.productivum.ru'):
            for secure in (False, True):
                for path in ('/home', '/home/'):
                    response = self.client.get(path + '?tag=a&tag=b', HTTP_HOST=host, secure=secure)
                    self.assertEqual(response.status_code, 301)
                    self.assertEqual(response['Location'], 'https://productivum.ru/?tag=a&tag=b')
                    final = self.client.get('/?tag=a&tag=b', HTTP_HOST='productivum.ru', secure=True)
                    self.assertEqual(final.status_code, 200)
                    self.assertNotIn('Location', final)

    def test_forwarded_headers_cannot_override_the_server_scheme_or_destination(self):
        spoof = {'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_X_FORWARDED_HOST': 'evil.example',
                 'HTTP_FORWARDED': 'proto=https;host=evil.example'}
        response = self.client.get('/', HTTP_HOST='productivum.ru', **spoof)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://productivum.ru/')
        response = self.client.get('/', HTTP_HOST='productivum.ru', secure=True, HTTP_X_FORWARDED_PROTO='http')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response)
        self.assertEqual(self.client.get('/', HTTP_HOST='evil.example').status_code, 400)

    @override_settings(CANONICAL_REDIRECTS_ENABLED=False, ALLOWED_HOSTS=['localhost', 'testserver'])
    def test_local_development_does_not_require_https_or_production_host(self):
        response = self.client.get('/', HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(self.client.get('/home/?x=1', HTTP_HOST='localhost'), '/?x=1', status_code=301, fetch_redirect_response=False)
