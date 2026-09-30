import json
import re
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse


class RemovedSectionsTests(SimpleTestCase):
    def test_removed_urls_do_not_resolve(self):
        for path in ('/todos/', '/todos/2026-09-30/', '/todos/add/',
                     '/todos/1/update/', '/todos/1/delete/', '/todos/load-todos/',
                     '/pomodoro/', '/home/math/', '/home/math/results/'):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_removed_names_cannot_be_reversed(self):
        for name in ('todos:index', 'todos:add', 'pomodoro:base',
                     'mathtraining', 'math_training_results'):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_archive_is_not_discovered_by_apps_templates_or_static(self):
        self.assertFalse(apps.is_installed('todos'))
        self.assertFalse(apps.is_installed('pomodoro'))
        self.assertFalse(any(app.name.startswith('archive') for app in apps.get_app_configs()))
        for name in ('todos/base.html', 'todos/index.html', 'pomodoro/index.html',
                     'general_app/mathtraining.html', 'general_app/mathtraining_results.html',
                     'archive/math/templates/general_app/mathtraining.html'):
            with self.subTest(template=name), self.assertRaises(TemplateDoesNotExist):
                get_template(name)
        for path in ('main.css', 'pomodoro/main.css', 'pomodoro/main.js',
                     'pomodoro/modal.css', 'end.mp3', 'font-awesome.min.css',
                     'general_app/css/math-main.css', 'general_app/css/math-result-main.css'):
            with self.subTest(static=path):
                self.assertIsNone(finders.find(path))
        self.assertIsNotNone(finders.find('hwyd/css/main.css'))
        self.assertIsNotNone(finders.find('hwyd/vendor/font-awesome/css/font-awesome.min.css'))


class StaticServingTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_local_whitenoise_serves_namespaced_source_without_collection(self):
        from whitenoise.middleware import WhiteNoiseMiddleware

        middleware = WhiteNoiseMiddleware(lambda request: HttpResponse(status=404))
        for asset in ('hwyd/css/main.css', 'chat/js/chat.js', 'site/css/navbar.css',
                      'notifications/css/modal.css'):
            with self.subTest(asset=asset):
                response = middleware(RequestFactory().get('/static/' + asset))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content),
                                 Path(finders.find(asset)).read_bytes())
                response.close()


class RemainingPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='remaining-pages')

    def assert_removed_links_absent(self, response):
        for fragment in ('/todos/', '/pomodoro/', '/home/math/',
                         'id="todoapp"', 'id="pomodorotimer"', 'id="mathtraining"'):
            self.assertNotContains(response, fragment)

    def test_public_pages_render_and_keep_authentication_links(self):
        for name in ('home', 'about', 'entry'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assert_removed_links_absent(response)
                self.assertContains(response, reverse('entry'))
        self.assertEqual(self.client.get(reverse('profile')).status_code, 302)

    def test_authenticated_pages_keep_habitus_profile_and_notifications(self):
        from notifications.models import Notification

        Notification.objects.create(title='Remaining notification', message='Still available')
        self.client.force_login(self.user)
        for name in ('home', 'about', 'profile'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assert_removed_links_absent(response)
                self.assertContains(response, reverse('index'))
                self.assertContains(response, reverse('profile'))
                self.assertContains(response, 'Remaining notification')

    def test_habitus_renders_desktop_and_mobile_with_chat(self):
        from notifications.models import Notification

        Notification.objects.create(message='Habitus notification')
        self.client.force_login(self.user)
        agents = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
            'AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1',
        )
        for agent in agents:
            with self.subTest(agent=agent):
                response = self.client.get(reverse('by_date', args=['2026-09']),
                                           HTTP_USER_AGENT=agent, HTTP_HOST='testserver')
                self.assertEqual(response.status_code, 200)
                self.assert_removed_links_absent(response)
                self.assertContains(response, reverse('chat:messages'))
                self.assertContains(response, reverse('notifications:mark-seen'))

    def test_notification_mark_seen_still_works(self):
        from notifications.models import Notification, NotificationSeen

        notification = Notification.objects.create(message='Test notification')
        url = reverse('notifications:mark-seen')
        self.assertEqual(self.client.post(url, {'id': notification.pk}).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url, {'id': notification.pk}).status_code, 200)
        self.assertTrue(NotificationSeen.objects.filter(notification=notification, user=self.user).exists())

    def test_rendered_pages_resolve_their_local_static_dependencies(self):
        from general_app.models import Guide
        from notifications.models import Notification

        Guide.objects.create(slug='main_toolbar', title='Toolbar')
        Notification.objects.create(message='Static dependency fixture')
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.client.force_login(self.user)
        paths = [reverse(name) for name in ('home', 'about', 'profile',
                                            'edit_settings', 'activity_users')]
        paths.append(reverse('by_date', args=['2026-09']))
        for path in paths:
            with self.subTest(page=path):
                response = self.client.get(path, HTTP_HOST='testserver')
                self.assertEqual(response.status_code, 200)
                assets = re.findall(r'(?:href|src)="/static/([^"?]+)',
                                    response.content.decode())
                self.assertTrue(assets)
                for asset in assets:
                    with self.subTest(asset=asset):
                        self.assertIsNotNone(finders.find(asset))

    def test_manifest_and_service_worker_keep_routes_and_resolve_icons(self):
        manifest = json.loads(Path(finders.find('hwyd/manifest_habitus.json')).read_text())
        self.assertEqual(manifest['start_url'], '/habitus')
        for icon in manifest['icons']:
            self.assertIsNotNone(finders.find(icon['src'].removeprefix('/static/')))
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        for asset in re.findall(r'/static/([^\s\x27\"]+)', response.content.decode()):
            self.assertIsNotNone(finders.find(asset))
