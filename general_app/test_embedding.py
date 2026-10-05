"""Narrow framing permissions and HTTPS session/CSRF integration."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from hwyd.models import Activities
from my_site.embedding import local_dashboard_frame_ancestors


POLICY = "frame-ancestors 'self' http://localhost:5173"


class FramePolicyTests(SimpleTestCase):
    def test_preserves_other_directives_in_each_existing_policy(self):
        original = ("default-src 'self'; frame-ancestors 'none'; script-src 'self' 'nonce-abc', "
                    "img-src 'self' data:; FRAME-ANCESTORS https://old.example; frame-ancestors *")

        @local_dashboard_frame_ancestors
        def view(request):
            return HttpResponse(headers={'Content-Security-Policy': original})

        response = view(RequestFactory().get('/'))
        self.assertEqual(response['Content-Security-Policy'],
                         f"default-src 'self'; script-src 'self' 'nonce-abc'; {POLICY}, "
                         f"img-src 'self' data:; {POLICY}")

    @override_settings(HABITUS_FRAME_ORIGINS=('http://localhost:5173', 'http://127.0.0.1:5173'))
    def test_loopback_ip_requires_an_explicit_separate_origin(self):
        response = local_dashboard_frame_ancestors(lambda request: HttpResponse())(RequestFactory().get('/'))
        self.assertEqual(response['Content-Security-Policy'], POLICY + ' http://127.0.0.1:5173')


class EmbeddingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('iframe-user', password='iframe-test-password-42')
        cls.month = '2026-10'
        cls.page = reverse('by_date', args=[cls.month])

    def assert_embeddable(self, response):
        self.assertNotIn('X-Frame-Options', response)
        self.assertEqual(response['Content-Security-Policy'], POLICY)
        self.assertNotIn('127.0.0.1', response['Content-Security-Policy'])

    def test_only_tracker_and_entry_have_frame_exemptions(self):
        for name in ('index', 'entry'):
            self.assert_embeddable(self.client.get(reverse(name), secure=True))
        self.assert_embeddable(self.client.get(self.page, secure=True))
        self.client.force_login(self.user)
        self.assert_embeddable(self.client.get(self.page, secure=True, HTTP_HOST='testserver'))
        for name in ('home', 'about', 'profile', 'edit_settings', 'admin:login'):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), secure=True, HTTP_HOST='testserver')
                self.assertEqual(response['X-Frame-Options'], 'DENY')
                self.assertNotIn('Content-Security-Policy', response)

    def csrf_client(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST='testserver')
        url = reverse('entry') + '?next=' + self.page
        response = client.get(url, secure=True)
        self.assert_embeddable(response)
        return client, url

    def login(self, client, url, **overrides):
        data = {'username': self.user.username, 'password': 'iframe-test-password-42', 'login': '',
                'csrfmiddlewaretoken': client.cookies[settings.CSRF_COOKIE_NAME].value}
        data.update(overrides)
        return client.post(url, data, secure=True, HTTP_ORIGIN='https://testserver')

    def test_https_login_create_and_save_with_csrf_protection(self):
        client, url = self.csrf_client()
        csrf_cookie = client.cookies[settings.CSRF_COOKIE_NAME]
        self.assertEqual(csrf_cookie['samesite'], 'None')
        self.assertTrue(csrf_cookie['secure'])
        response = self.login(client, url)
        self.assertRedirects(response, self.page, fetch_redirect_response=False)
        self.assert_embeddable(response)
        session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(session_cookie['samesite'], 'None')
        self.assertTrue(session_cookie['secure'])
        self.assertTrue(session_cookie['httponly'])
        self.assert_embeddable(client.get(self.page, secure=True))
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(reverse('create_activity', args=[self.month, 0]),
                               {'createActivityInput': 'Iframe habit', 'csrfmiddlewaretoken': token},
                               secure=True, HTTP_ORIGIN='https://testserver')
        self.assertRedirects(response, self.page, fetch_redirect_response=False)
        habit = Activities.objects.get(user=self.user, name='Iframe habit')
        mark_url = reverse('check_cell', args=[self.month])
        response = client.post(mark_url, {'checkboxToCheck': '0-0', 'csrfmiddlewaretoken': token},
                               secure=True, HTTP_ORIGIN='https://testserver')
        self.assertEqual(response.status_code, 200)
        habit.refresh_from_db()
        self.assertEqual(habit.marks.split()[0], 'True')
        for origin, csrf in [('https://testserver', ''), ('http://localhost:5173', token)]:
            with self.subTest(origin=origin, csrf=bool(csrf)):
                response = client.post(mark_url, {'checkboxToCheck': '0-0', 'csrfmiddlewaretoken': csrf},
                                       secure=True, HTTP_ORIGIN=origin)
                self.assertEqual(response.status_code, 403)
        habit.refresh_from_db()
        self.assertEqual(habit.marks.split()[0], 'True')

    def test_login_still_rejects_missing_csrf_token(self):
        client, url = self.csrf_client()
        self.assertEqual(self.login(client, url, csrfmiddlewaretoken='').status_code, 403)
        self.assertNotIn('_auth_user_id', client.session)
