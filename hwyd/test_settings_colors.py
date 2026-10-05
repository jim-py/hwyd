"""Temporary Settings palette: owner isolation, validation, and no schedule dependency."""
from datetime import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Settings, ScheduledTheme
from .preferences import THEME_COLOR_FIELDS, THEME_COLOR_DEFAULTS
from .views import create_setting


@override_settings(USE_SCHEDULED_THEME_COLORS=False)
class SettingsColorsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('settings-colors')
        cls.other = get_user_model().objects.create_user('other-colors')
        cls.admin = get_user_model().objects.create_superuser('colors-preview', password='test')
        create_setting(cls.user, 'Selected')
        create_setting(cls.other, 'Other')
        cls.preset = Settings.objects.get(user=cls.user)
        cls.colors = dict(zip(THEME_COLOR_FIELDS, ('#123456', '#234567', '#345678', '#456789', '#56789a')))
        Settings.objects.filter(pk=cls.preset.pk).update(**cls.colors)
        cls.preset.refresh_from_db()
        cls.theme = ScheduledTheme.objects.create(user=cls.user, name='Unused', activation_time=time(0),
                                                  **dict.fromkeys(THEME_COLOR_FIELDS, '#abcdef'))

    def setUp(self):
        self.client.force_login(self.user)
        self.page = reverse('by_date', args=['2026-10'])

    def test_settings_palette_on_both_pages_and_legacy_schedule_api(self):
        session = self.client.session
        session['habitus_display_colors'] = dict.fromkeys(THEME_COLOR_FIELDS, '#abcdef')
        session['habitus_display_theme'] = self.theme.pk
        session['habitus_manual_theme_until'] = {'theme_id': self.theme.pk, 'expires_at': 9999999999}
        session.save()
        page = self.client.get(self.page, HTTP_HOST='testserver')
        self.assertEqual(page.context['theme_palette'], self.colors)
        self.assertNotContains(page, 'hwyd/js/theme-schedule.js')
        self.assertNotContains(page, 'id="themeScheduleButton"')
        settings_page = self.client.get(reverse('edit_settings'))
        fields = {field.name: field.value() for field in settings_page.context['settings_fields']}
        self.assertEqual({field: fields[field] for field in THEME_COLOR_FIELDS}, self.colors)
        for name, method in [('theme_schedule_list', 'get'), ('theme_schedule_apply', 'post')]:
            state = getattr(self.client, method)(reverse(name)).json()
            self.assertEqual(state['colors'], self.colors)
            self.assertIsNone(state['next_change_at'])
            self.assertEqual(state['themes'], [])

    def test_color_save_only_updates_own_selected_settings_and_validates_all_fields(self):
        create_setting(self.user, 'Unselected')
        Settings.objects.filter(user=self.user).exclude(pk=self.preset.pk).update(selected=False)
        before_others = list(Settings.objects.exclude(pk=self.preset.pk).values())
        before_themes = list(ScheduledTheme.objects.values())
        colors = dict.fromkeys(THEME_COLOR_FIELDS, '#6789ab')
        url = reverse('global_colors', args=['2026-10'])
        for field in THEME_COLOR_FIELDS:
            self.assertEqual(self.client.post(url, {**colors, field: 'invalid'}).status_code, 400)
        self.assertEqual(self.client.post(url, colors).status_code, 302)
        self.preset.refresh_from_db()
        self.assertEqual({field: getattr(self.preset, field) for field in THEME_COLOR_FIELDS}, colors)
        self.assertEqual(list(Settings.objects.exclude(pk=self.preset.pk).values()), before_others)
        self.assertEqual(list(ScheduledTheme.objects.values()), before_themes)

    def test_settings_page_saves_colors_and_preferences_atomically(self):
        colors = dict.fromkeys(THEME_COLOR_FIELDS, '#678abc')
        data = {**model_to_dict(self.preset), **colors, 'fontFamily': 'Georgia',
                'vanishing': 'none', 'uiVisibilityVersion': '4'}
        before_themes = list(ScheduledTheme.objects.values())
        self.assertEqual(self.client.post(reverse('edit_settings'), data).status_code, 302)
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.fontFamily, 'Georgia')
        self.assertEqual({field: getattr(self.preset, field) for field in THEME_COLOR_FIELDS}, colors)
        data.update(backgroundColor='invalid', fontFamily='Arial')
        self.assertEqual(self.client.post(reverse('edit_settings'), data).status_code, 200)
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.fontFamily, 'Georgia')
        self.assertEqual(self.preset.backgroundColor, '#678abc')
        self.assertEqual(list(ScheduledTheme.objects.values()), before_themes)

    def test_preset_switch_changes_the_palette(self):
        Settings.objects.filter(user=self.user).update(selected=False)
        create_setting(self.user, 'Another')
        self.assertEqual(self.client.get(self.page, HTTP_HOST='testserver').context['theme_palette'], THEME_COLOR_DEFAULTS)
        self.assertEqual(self.client.get(reverse('select_setting', args=[self.preset.pk])).status_code, 302)
        self.assertEqual(self.client.get(self.page, HTTP_HOST='testserver').context['theme_palette'], self.colors)

    def test_read_only_preview_uses_target_settings_and_cannot_save(self):
        self.client.force_login(self.admin)
        page = self.client.get(self.page, {'view_as': self.user.pk}, HTTP_HOST='testserver')
        self.assertEqual(page.context['theme_palette'], self.colors)
        state = self.client.get(reverse('theme_schedule_list'), {'view_as': self.user.pk}).json()
        self.assertEqual(state['colors'], self.colors)
        url = reverse('global_colors', args=['2026-10']) + f'?view_as={self.user.pk}'
        self.assertEqual(self.client.post(url, dict.fromkeys(THEME_COLOR_FIELDS, '#ffffff')).status_code, 403)
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, self.colors['backgroundColor'])

    def test_runtime_does_not_access_scheduled_theme_table(self):
        with patch.object(ScheduledTheme.objects, 'filter', side_effect=AssertionError('Unexpected schedule query')):
            self.assertEqual(self.client.get(self.page, HTTP_HOST='testserver').status_code, 200)
            self.assertEqual(self.client.get(reverse('edit_settings')).status_code, 200)
            self.assertEqual(self.client.post(reverse('global_colors', args=['2026-10']), self.colors).status_code, 302)
            self.assertEqual(self.client.post(reverse('theme_schedule_apply')).status_code, 200)
            self.assertEqual(self.client.post(reverse('theme_schedule_create')).status_code, 503)
            self.assertEqual(self.client.post(reverse('theme_schedule_delete', args=[self.theme.pk])).status_code, 503)

    def test_new_user_gets_settings_defaults_without_creating_scheduled_themes(self):
        user = get_user_model().objects.create_user('new-settings-colors')
        self.client.force_login(user)
        before = ScheduledTheme.objects.count()
        page = self.client.get(self.page, HTTP_HOST='testserver')
        self.assertEqual(page.context['theme_palette'], THEME_COLOR_DEFAULTS)
        self.assertTrue(Settings.objects.filter(user=user, selected=True).exists())
        self.assertEqual(ScheduledTheme.objects.count(), before)
