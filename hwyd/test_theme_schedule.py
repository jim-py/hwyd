from datetime import datetime, time, timezone as utc_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import ScheduledTheme, Settings
from .preferences import THEME_COLOR_FIELDS
from .theme_schedule import current_theme, next_activation, schedule_state
from .timezones import browser_timezone
from .views import create_setting


class ThemeScheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='theme-owner')
        cls.other = get_user_model().objects.create_user(username='theme-other')
        create_setting(cls.user, 'Current')
        create_setting(cls.other, 'Other')

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['user_timezone'] = 'Europe/Moscow'
        session.save()
        self.preset = Settings.objects.get(user=self.user)
        self.colors = {field: getattr(self.preset, field) for field in THEME_COLOR_FIELDS}
        self.now = datetime(2026, 10, 4, 9, tzinfo=utc_timezone.utc) # noon in Moscow
        now = patch('hwyd.theme_schedule.timezone.now', return_value=self.now)
        now.start()
        self.addCleanup(now.stop)

    def create(self, **data):
        return self.client.post(reverse('theme_schedule_create'),
                                {'name': 'Светлая', 'activation_time': '08:00', **data}, content_type='application/json')

    def theme(self, name='Светлая', hour=8, user=None, enabled=True, **colors):
        return ScheduledTheme.objects.create(user=user or self.user, name=name, activation_time=time(hour),
                                              is_enabled=enabled, **{**self.colors, **colors})

    def update(self, theme, **data):
        return self.client.patch(reverse('theme_schedule_update', args=[theme.pk]), data, content_type='application/json')

    def test_create_copies_only_selected_owners_persisted_colors(self):
        create_setting(self.user, 'Not selected')
        Settings.objects.filter(user=self.user).exclude(pk=self.preset.pk).update(selected=False, backgroundColor='#abcdef')
        response = self.create(name='  Светлая  ', user=self.other.pk, backgroundColor='#000000')
        self.assertEqual(response.status_code, 201)
        theme = ScheduledTheme.objects.get()
        self.assertEqual(theme.user, self.user)
        self.assertEqual(theme.name, 'Светлая')
        self.assertEqual(theme.activation_time, time(8))
        for field, value in self.colors.items():
            self.assertEqual(getattr(theme, field), value)
        self.assertTrue(response.json()['success'])
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, self.colors['backgroundColor'])

    def test_list_is_own_and_read_only_and_has_no_n_plus_one(self):
        for hour in range(12):
            self.theme(name=f'Theme {hour}', hour=hour, backgroundColor='#010203')
        foreign = self.theme(user=self.other, name='Secret')
        response = self.client.get(reverse('theme_schedule_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(foreign.pk, [item['id'] for item in response.json()['themes']])
        self.assertNotContains(response, 'Secret')
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, self.colors['backgroundColor'])
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.user, request.session = self.user, {'user_timezone': 'Europe/Moscow'}
        with self.assertNumQueries(2):
            schedule_state(request)

    def test_cannot_read_edit_or_delete_foreign_theme(self):
        foreign = self.theme(user=self.other)
        self.assertEqual(self.update(foreign, name='Hacked').status_code, 404)
        response = self.client.delete(reverse('theme_schedule_delete', args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.name, 'Светлая')

    def test_update_changes_metadata_but_never_snapshot(self):
        theme = self.theme()
        Settings.objects.filter(pk=self.preset.pk).update(backgroundColor='#111111')
        response = self.update(theme, name='Утро', activation_time='09:30', is_enabled=False)
        self.assertEqual(response.status_code, 200)
        theme.refresh_from_db()
        self.assertEqual((theme.name, theme.activation_time, theme.is_enabled, theme.active_time), ('Утро', time(9, 30), False, None))
        self.assertEqual(theme.backgroundColor, self.colors['backgroundColor'])
        self.assertEqual(self.update(theme, backgroundColor='#222222').status_code, 400)

    def test_delete_recalculates_and_keeps_last_colors_if_none_enabled(self):
        light = self.theme()
        dark = self.theme('Тёмная', hour=20, backgroundColor='#121212')
        self.assertEqual(self.client.delete(reverse('theme_schedule_delete', args=[light.pk])).status_code, 200)
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, '#121212')
        response = self.client.delete(reverse('theme_schedule_delete', args=[dark.pk]))
        self.assertEqual(response.json()['themes'], [])
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, '#121212')

    def test_daily_boundaries_midnight_and_closed_browser(self):
        light = self.theme()
        dark = self.theme('Тёмная', hour=20)
        tz = browser_timezone('Europe/Moscow')
        for hour, minute, expected in ((0, 0, dark), (7, 0, dark), (8, 0, light), (12, 0, light),
                                       (19, 59, light), (20, 0, dark), (23, 59, dark)):
            with self.subTest(hour=hour, minute=minute):
                now = datetime(2026, 10, 4, hour, minute, tzinfo=tz)
                self.assertEqual(current_theme([light, dark], now, tz), expected)
                self.assertGreater(next_activation([light, dark], now, tz), now.astimezone(utc_timezone.utc))
        with patch('hwyd.theme_schedule.timezone.now', return_value=datetime(2026, 10, 4, 19, tzinfo=utc_timezone.utc)):
            response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['theme_schedule_state']['active_id'], dark.pk)

    def test_timezone_controls_selection_and_unknown_timezone_does_not_guess(self):
        light = self.theme()
        dark = self.theme('Тёмная', hour=20, backgroundColor='#111111')
        for name, expected in [('Europe/Moscow', light), ('Asia/Tokyo', light), ('America/New_York', dark)]:
            session = self.client.session
            session['user_timezone'] = name
            session.save()
            response = self.client.post(reverse('theme_schedule_apply'))
            self.assertEqual(response.json()['active_id'], expected.pk)
            self.assertEqual(response.json()['timezone'], name)
        session = self.client.session
        session.pop('user_timezone')
        session.save()
        response = self.client.post(reverse('theme_schedule_apply'))
        self.assertIsNone(response.json()['active_id'])
        self.assertIsNone(response.json()['next_change_at'])
        self.assertIsNone(response.json()['timezone'])

    def test_disabled_themes_do_not_participate_and_toggle_applies_immediately(self):
        light = self.theme()
        disabled = self.theme('Другая', hour=10, enabled=False, backgroundColor='#101010')
        response = self.client.post(reverse('theme_schedule_apply'))
        self.assertEqual(response.json()['active_id'], light.pk)
        self.assertEqual(self.update(disabled, is_enabled=True).json()['active_id'], disabled.pk)
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, '#101010')
        self.assertEqual(self.update(disabled, is_enabled=False).json()['active_id'], light.pk)

    def test_duplicate_active_times_are_validated_and_database_protected(self):
        original = self.theme()
        response = self.create()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'На 08:00 уже назначена другая тема.')
        disabled = self.theme('Отключена', hour=8, enabled=False)
        self.assertEqual(self.update(disabled, is_enabled=True).status_code, 400)
        self.assertEqual(self.update(disabled, is_enabled=True, activation_time='09:00').status_code, 200)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.theme('Concurrent duplicate', hour=8)
        self.assertTrue(ScheduledTheme.objects.filter(pk=original.pk).exists())

    def test_empty_schedule_does_not_write_settings(self):
        response = self.client.post(reverse('theme_schedule_apply'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['themes'], [])
        self.assertFalse(response.json()['changed'])
        self.assertIsNone(response.json()['next_change_at'])

    def test_repeated_apply_does_not_write_unchanged_settings(self):
        self.theme(backgroundColor='#111111')
        self.assertTrue(self.client.post(reverse('theme_schedule_apply')).json()['changed'])
        self.assertFalse(self.client.post(reverse('theme_schedule_apply')).json()['changed'])

    def test_invalid_payloads_and_colors_are_errors_not_server_errors(self):
        for data in ({'name': '  '}, {'name': 'x' * 81}, {'activation_time': '25:00'},
                     {'activation_time': '08:00:01'}, {'activation_time': []}, {'name': []}, {'is_enabled': 'false'}):
            with self.subTest(data=data):
                self.assertEqual(self.create(**data).status_code, 400)
        for body in ('[1,2]', 'bad JSON'):
            self.assertEqual(self.client.post(reverse('theme_schedule_create'), body, content_type='application/json').status_code, 400)
        Settings.objects.filter(pk=self.preset.pk).update(backgroundColor='bad css')
        self.assertEqual(self.create().status_code, 400)
        self.assertFalse(ScheduledTheme.objects.exists())

    def test_authorization_csrf_and_methods(self):
        theme = self.theme()
        self.client.logout()
        for name, method, args in [('theme_schedule_list', 'get', []), ('theme_schedule_create', 'post', []),
                                   ('theme_schedule_update', 'patch', [theme.pk]), ('theme_schedule_delete', 'delete', [theme.pk]),
                                   ('theme_schedule_apply', 'post', [])]:
            self.assertEqual(getattr(self.client, method)(reverse(name, args=args)).status_code, 401)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for name, method, args in [('theme_schedule_create', 'post', []), ('theme_schedule_update', 'patch', [theme.pk]),
                                   ('theme_schedule_delete', 'delete', [theme.pk]), ('theme_schedule_apply', 'post', [])]:
            self.assertEqual(getattr(client, method)(reverse(name, args=args)).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('theme_schedule_create')).status_code, 405)
        self.assertEqual(self.client.get(reverse('theme_schedule_apply')).status_code, 405)

    def test_manual_colors_allow_second_snapshot_until_next_event(self):
        light = self.theme()
        response = self.client.post(reverse('global_colors', args=['2026-10']), {**self.colors, 'backgroundColor': '#101010'})
        self.assertEqual(response.status_code, 302)
        page = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
        self.assertTrue(page.context['theme_schedule_state']['manual_override'])
        self.assertEqual(page.context['settings'].backgroundColor, '#101010')
        dark = self.create(name='Тёмная', activation_time='20:00').json()['theme']
        self.assertEqual(dark['colors']['backgroundColor'], '#101010')
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, self.colors['backgroundColor'])
        response = self.client.post(reverse('global_colors', args=['2026-10']), {**self.colors, 'backgroundColor': '#333333'})
        with patch('hwyd.theme_schedule.timezone.now', return_value=datetime(2026, 10, 4, 18, tzinfo=utc_timezone.utc)):
            state = self.client.post(reverse('theme_schedule_apply')).json()
        self.assertFalse(state['manual_override'])
        self.assertEqual(state['active_id'], dark['id'])
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, '#101010')
        light.refresh_from_db()
        self.assertEqual(light.backgroundColor, self.colors['backgroundColor'])

    def test_ui_includes_endpoints_and_safe_initial_data_on_desktop_and_mobile(self):
        theme = self.theme(name='<img src=x onerror=alert(1)>')
        for agent in ('Desktop', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148 Safari/604.1'):
            response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver', HTTP_USER_AGENT=agent)
            self.assertContains(response, 'id="themeScheduleButton"', count=1)
            self.assertContains(response, 'id="themeScheduleModal"', count=1)
            self.assertContains(response, reverse('theme_schedule_apply'))
            self.assertContains(response, 'hwyd/js/theme-schedule.js')
            self.assertNotContains(response, theme.name)
            self.assertContains(response, '\\u003Cimg')

    def test_hidden_toolbar_button_keeps_automatic_schedule_on_desktop_and_mobile(self):
        theme = self.theme(backgroundColor='#123456')
        Settings.objects.filter(pk=self.preset.pk).update(showThemeSchedule=False)
        for agent in ('Desktop', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148 Safari/604.1'):
            response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver', HTTP_USER_AGENT=agent)
            self.assertContains(response, 'aria-label="Расписание тем" hidden')
            self.assertContains(response, 'id="themeScheduleModal"', count=1)
            self.assertContains(response, 'hwyd/js/theme-schedule.js')
            self.assertEqual(response.context['theme_schedule_state']['active_id'], theme.pk)
            self.assertEqual(response.context['settings'].backgroundColor, '#123456')
            state = self.client.post(reverse('theme_schedule_apply')).json()
            self.assertEqual(state['active_id'], theme.pk)
        theme.refresh_from_db()
        self.assertTrue(theme.is_enabled)

    def test_dst_gap_and_repeat_have_matching_selection_and_next_event(self):
        previous = self.theme('Previous', hour=0)
        event = self.theme('Event', hour=2)
        event.activation_time = time(2, 30)
        tz = browser_timezone('America/New_York')
        # On spring-forward day 02:30 becomes 03:30, matching both helper functions.
        now = datetime(2026, 3, 8, 7, 10, tzinfo=utc_timezone.utc)
        self.assertEqual(current_theme([previous, event], now, tz), previous)
        self.assertEqual(next_activation([previous, event], now, tz), datetime(2026, 3, 8, 7, 30, tzinfo=utc_timezone.utc))
        event.activation_time = time(1, 45)
        now = datetime(2026, 11, 1, 6, 10, tzinfo=utc_timezone.utc) # repeated 01:10
        self.assertEqual(current_theme([previous, event], now, tz), event)
        self.assertGreater(next_activation([previous, event], now, tz), now)
