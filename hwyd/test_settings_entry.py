"""The removed editor's bookmarks lead to the existing tracker dialog."""
from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.test import Client, TestCase
from django.urls import reverse

from .models import Settings, ScheduledTheme
from .views import create_setting


class SettingsEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('modal-settings-entry')
        create_setting(cls.user, 'Selected')

    def test_old_addresses_and_head_redirect_without_rendering_or_changing_preferences(self):
        self.client.force_login(self.user)
        before = list(Settings.objects.values())
        themes = list(ScheduledTheme.objects.values())
        for path in ('/habitus/settings', reverse('edit_settings')):
            for method in ('get', 'head'):
                response = getattr(self.client, method)(path)
                self.assertRedirects(response, reverse('index') + '#settings', fetch_redirect_response=False)
                self.assertEqual(response.templates, [])
        self.assertEqual(list(Settings.objects.values()), before)
        self.assertEqual(list(ScheduledTheme.objects.values()), themes)

    def test_old_bookmark_still_requires_login_then_reaches_the_real_dialog(self):
        path = reverse('edit_settings')
        self.assertRedirects(self.client.get(path), reverse('entry') + '?next=' + path, fetch_redirect_response=False)
        self.client.force_login(self.user)
        response = self.client.get(path, follow=True, HTTP_HOST='testserver')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'hwyd/base.html')
        self.assertContains(response, 'id="some-modal-id"', count=1)
        self.assertNotContains(response, 'Редактирование настроек')
        self.assertNotContains(response, 'hwyd/css/settings.css')

    def test_legacy_post_stays_validated_csrf_protected_and_redirects_to_dialog(self):
        self.client.force_login(self.user)
        preset = Settings.objects.get(user=self.user)
        data = {**model_to_dict(preset), 'fontFamily': 'Georgia', 'vanishing': 'none', 'uiVisibilityVersion': '4'}
        response = self.client.post(reverse('edit_settings'), data)
        self.assertRedirects(response, reverse('index') + '#settings', fetch_redirect_response=False)
        preset.refresh_from_db()
        self.assertEqual(preset.fontFamily, 'Georgia')
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(reverse('edit_settings'), data).status_code, 403)

    def test_preview_cannot_write_through_legacy_settings_endpoint(self):
        admin = get_user_model().objects.create_superuser('modal-settings-admin', password='local-test')
        self.client.force_login(admin)
        before = list(Settings.objects.values())
        response = self.client.post(reverse('edit_settings') + f'?view_as={self.user.pk}', {'fontFamily': 'Arial'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list(Settings.objects.values()), before)
