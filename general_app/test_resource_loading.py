"""Guard the rendered resource graph, including inheritance and shared includes."""
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from hwyd.models import Settings
from notifications.models import Notification


class ResourceGraph(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.in_head = False
        self.styles = []
        self.scripts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'head':
            self.in_head = True
        elif tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.styles.append((urlsplit(attrs['href']).path, self.in_head))
        elif tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs)

    def handle_endtag(self, tag):
        if tag == 'head':
            self.in_head = False


class ResourceLoadingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='resource-loading', is_staff=True)
        Notification.objects.create(title='Loading test', message='An unread announcement')

    def graph(self, page, mobile=False):
        response = self.client.get(reverse(page, args=['2026-10'] if page == 'by_date' else []),
                                   HTTP_HOST='testserver', HTTP_USER_AGENT=(
                                       'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                                       'Mobile/15E148 Safari/604.1' if mobile else 'Mozilla/5.0'))
        self.assertEqual(response.status_code, 200)
        return ResourceGraph(response.content.decode())

    def test_layout_styles_are_in_head_without_duplicate_icons_or_import_waterfall(self):
        for signed_in in (False, True):
            if signed_in:
                self.client.force_login(self.user)
            pages = ['home', 'about'] + (['profile', 'edit_settings', 'by_date', 'activity_users']
                                         if signed_in else ['entry'])
            for page in pages:
                for mobile in (False, True):
                    with self.subTest(page=page, signed_in=signed_in, mobile=mobile):
                        graph = self.graph(page, mobile)
                        paths = [path for path, _ in graph.styles]
                        self.assertTrue(all(head for _, head in graph.styles))
                        self.assertEqual(len(paths), len(set(paths)))
                        icons = [path for path in paths if 'font-awesome/' in path]
                        self.assertEqual(icons, ['/static/hwyd/vendor/font-awesome/7.3.1/css/all.min.css'])
                        self.assertIn('/static/site/css/navbar.css', paths)
                        self.assertIn('/static/site/vendor/google-fonts/fonts.css', paths)
                        for path in paths:
                            with open(finders.find(path.removeprefix('/static/')), encoding='utf-8') as css:
                                self.assertNotIn('@import', css.read(), path)

    def test_general_pages_do_not_load_unused_vendor_javascript(self):
        self.client.force_login(self.user)
        for page in ['home', 'about', 'profile', 'edit_settings', 'activity_users']:
            with self.subTest(page=page):
                scripts = self.graph(page).scripts
                for script in scripts:
                    self.assertNotIn('jquery', script['src'])
                    self.assertNotIn('bootstrap', script['src'])
                    self.assertNotIn('tailwind', script['src'])
                    self.assertTrue('defer' in script or script.get('type') == 'module')

    def test_tracker_has_one_deferred_jquery_before_ui_and_no_blocking_external_script(self):
        self.client.force_login(self.user)
        for mobile in (False, True):
            scripts = self.graph('by_date', mobile).scripts
            jquery = [s for s in scripts if '/jquery/' in s['src']]
            ui = [s for s in scripts if '/jquery-ui/' in s['src']]
            self.assertEqual(len(jquery), 1)
            self.assertEqual(len(ui), 1)
            self.assertTrue(jquery[0]['src'].endswith('/jquery.min.js'))
            self.assertLess(scripts.index(jquery[0]), scripts.index(ui[0]))
            self.assertTrue(all('defer' in s or s.get('type') == 'module' for s in scripts))

    def test_disabled_calendar_and_streak_do_not_request_their_assets(self):
        self.client.force_login(self.user)
        self.graph('by_date')  # The tracker creates a user's initial display preset.
        Settings.objects.filter(user=self.user).update(showViewSwitch=False, showStreak=False)
        graph = self.graph('by_date')
        paths = [path for path, _ in graph.styles] + [s['src'] for s in graph.scripts]
        self.assertFalse(any('year-calendar' in path or 'streak-firework' in path for path in paths))

