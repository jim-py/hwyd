from datetime import datetime, time, timezone as utc_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import ScheduledTheme, Settings
from .preferences import THEME_COLOR_FIELDS, THEME_COLOR_DEFAULTS, validate_theme_color
from .theme_schedule import current_theme, next_activation, schedule_state, ensure_default_themes
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
        self.colors = THEME_COLOR_DEFAULTS.copy()
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

    def test_create_copies_only_current_owners_scheduled_theme_colors(self):
        create_setting(self.user, 'Not selected')
        Settings.objects.filter(user=self.user).exclude(pk=self.preset.pk).update(selected=False, backgroundColor='#abcdef')
        source = self.theme(backgroundColor='#345678')
        self.theme(user=self.other, backgroundColor='#fedcba')
        response = self.create(name='  Светлая  ', activation_time='09:00', user=self.other.pk, backgroundColor='#000000')
        self.assertEqual(response.status_code, 201)
        theme = ScheduledTheme.objects.get(pk=response.json()['theme']['id'])
        self.assertEqual(theme.user, self.user)
        self.assertEqual(theme.name, 'Светлая')
        self.assertEqual(theme.activation_time, time(9))
        for field in THEME_COLOR_FIELDS:
            self.assertEqual(getattr(theme, field), getattr(source, field))
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
        with self.assertNumQueries(1):
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

    def test_delete_recalculates_without_writing_settings_or_bootstrapping(self):
        light = self.theme()
        dark = self.theme('Тёмная', hour=20, backgroundColor='#121212')
        response = self.client.delete(reverse('theme_schedule_delete', args=[light.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['colors']['backgroundColor'], '#121212')
        response = self.client.delete(reverse('theme_schedule_delete', args=[dark.pk]))
        self.assertEqual(response.json()['themes'], [])
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.backgroundColor, self.colors['backgroundColor'])
        self.assertIsNone(response.json()['colors'])

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
        self.assertEqual(self.preset.backgroundColor, self.colors['backgroundColor'])
        self.assertEqual(self.client.post(reverse('theme_schedule_apply')).json()['colors']['backgroundColor'], '#101010')
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

    def test_repeated_apply_reports_color_changes_without_writing_settings(self):
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
        ScheduledTheme.objects.all().delete()
        self.theme(backgroundColor='bad css')
        self.assertEqual(self.create(activation_time='09:00').status_code, 400)
        self.assertEqual(ScheduledTheme.objects.count(), 1)

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
        self.assertEqual(page.context['theme_palette']['backgroundColor'], '#101010')
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
        self.assertEqual(self.preset.backgroundColor, self.colors['backgroundColor'])
        self.assertEqual(state['colors']['backgroundColor'], '#101010')
        light.refresh_from_db()
        self.assertEqual(light.backgroundColor, '#333333')

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
            self.assertEqual(response.context['theme_palette']['backgroundColor'], '#123456')
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


    def test_empty_page_bootstraps_two_valid_themes_once_per_owner(self):
        self.theme(user=self.other, name='Other existing theme')
        for page in ('by_date', 'edit_settings', 'by_date'):
            response = self.client.get(reverse(page, args=['2026-10'] if page == 'by_date' else []), HTTP_HOST='testserver')
            self.assertEqual(response.status_code, 200)
            themes = list(ScheduledTheme.objects.filter(user=self.user))
            self.assertEqual([(t.name, t.activation_time, t.is_enabled) for t in themes],
                             [('Светлая', time(8), True), ('Тёмная', time(20), True)])
            for theme in themes:
                theme.full_clean()
                for field in THEME_COLOR_FIELDS:
                    validate_theme_color(getattr(theme, field))
            if page == 'by_date':
                self.assertEqual(response.context['theme_palette'], self.colors)
        ensure_default_themes(self.user)
        self.assertEqual(ScheduledTheme.objects.filter(user=self.user).count(), 2)
        self.assertEqual(ScheduledTheme.objects.filter(user=self.other).count(), 1)

    def test_settings_page_also_bootstraps_without_an_interface_preset(self):
        Settings.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.get(reverse('edit_settings')).status_code, 200)
        self.assertEqual(ScheduledTheme.objects.filter(user=self.user).count(), 2)

    def test_existing_disabled_custom_theme_is_not_bootstrapped_or_overwritten(self):
        custom = self.theme(name='Custom', enabled=False, backgroundColor='#123456')
        before = list(ScheduledTheme.objects.values())
        response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
        self.assertEqual(response.context['theme_palette']['backgroundColor'], '#123456')
        self.assertIsNone(response.context['theme_schedule_state']['active_id'])
        self.assertEqual(list(ScheduledTheme.objects.values()), before)
        custom.refresh_from_db()
        self.assertFalse(custom.is_enabled)

    def test_all_five_runtime_colors_ignore_legacy_settings_on_both_pages(self):
        colors = dict(zip(THEME_COLOR_FIELDS, ('#234567', '#345678', '#456789', '#56789a', '#6789ab')))
        theme = self.theme(**colors)
        for legacy in ('#abcdef', '#fedcba'):
            Settings.objects.filter(pk=self.preset.pk).update(**dict.fromkeys(THEME_COLOR_FIELDS, legacy))
            page = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
            self.assertEqual(page.context['theme_palette'], colors)
            self.assertEqual(page.context['theme_schedule_state']['active_id'], theme.pk)
            for field, value in colors.items():
                self.assertContains(page, f'value="{value}"')
            page = self.client.get(reverse('edit_settings'))
            fields = {field.name: field.value() for field in page.context['settings_fields']}
            self.assertEqual({field: fields[field] for field in THEME_COLOR_FIELDS}, colors)
            state = self.client.get(reverse('theme_schedule_list')).json()
            self.assertEqual(state['colors'], colors)

    def test_color_update_validates_and_updates_only_own_current_theme(self):
        theme = self.theme()
        later = self.theme(name='Later', hour=20)
        foreign = self.theme(user=self.other)
        before = list(Settings.objects.order_by('pk').values())
        colors = dict.fromkeys(THEME_COLOR_FIELDS, '#123abc')
        url = reverse('global_colors', args=['2026-10'])
        self.assertEqual(self.client.post(url, {**colors, 'backgroundColor': 'bad css'}).status_code, 400)
        theme.refresh_from_db()
        self.assertEqual(theme.backgroundColor, self.colors['backgroundColor'])
        self.assertEqual(self.client.post(url, colors).status_code, 302)
        theme.refresh_from_db()
        self.assertEqual({field: getattr(theme, field) for field in THEME_COLOR_FIELDS}, colors)
        for untouched in (later, foreign):
            untouched.refresh_from_db()
            self.assertEqual(untouched.backgroundColor, self.colors['backgroundColor'])
        self.assertEqual(list(Settings.objects.order_by('pk').values()), before)

    def test_settings_page_saves_colors_to_theme_and_other_preferences_to_settings(self):
        from django.forms.models import model_to_dict
        theme = self.theme(backgroundColor='#123456')
        colors = dict.fromkeys(THEME_COLOR_FIELDS, '#234567')
        data = {**model_to_dict(self.preset), **colors, 'fontFamily': 'Georgia', 'vanishing': 'none', 'uiVisibilityVersion': '4'}
        response = self.client.post(reverse('edit_settings'), data)
        self.assertEqual(response.status_code, 302)
        theme.refresh_from_db()
        self.assertEqual({field: getattr(theme, field) for field in THEME_COLOR_FIELDS}, colors)
        self.preset.refresh_from_db()
        self.assertEqual(self.preset.fontFamily, 'Georgia')
        self.assertEqual({field: getattr(self.preset, field) for field in THEME_COLOR_FIELDS}, self.colors)
        data.update(backgroundColor='invalid', fontFamily='Arial')
        response = self.client.post(reverse('edit_settings'), data)
        self.assertEqual(response.status_code, 200)
        self.preset.refresh_from_db()
        theme.refresh_from_db()
        self.assertEqual(self.preset.fontFamily, 'Georgia')
        self.assertEqual(theme.backgroundColor, '#234567')

    def test_missing_timezone_and_disabled_schedule_retain_scheduled_theme_colors(self):
        light = self.theme(backgroundColor='#123456')
        dark = self.theme(name='Night', hour=20, backgroundColor='#abcdef')
        self.assertEqual(self.client.post(reverse('theme_schedule_apply')).json()['active_id'], light.pk)
        session = self.client.session
        session.pop('user_timezone')
        session.save()
        state = self.client.post(reverse('theme_schedule_apply')).json()
        self.assertIsNone(state['active_id'])
        self.assertEqual(state['colors']['backgroundColor'], '#123456')
        self.update(light, is_enabled=False)
        self.update(dark, is_enabled=False)
        state = self.client.post(reverse('theme_schedule_apply')).json()
        self.assertEqual(state['colors']['backgroundColor'], '#123456')

    def test_selecting_interface_settings_does_not_change_theme_colors(self):
        theme = self.theme(backgroundColor='#123456')
        create_setting(self.user, 'Another preset')
        another = Settings.objects.filter(user=self.user).latest('pk')
        Settings.objects.filter(user=self.user).update(selected=False)
        Settings.objects.filter(pk=self.preset.pk).update(selected=True)
        self.client.get(reverse('select_setting', args=[another.pk]))
        state = self.client.post(reverse('theme_schedule_apply')).json()
        self.assertEqual(state['active_id'], theme.pk)
        self.assertEqual(state['colors']['backgroundColor'], '#123456')
        self.assertFalse(state['manual_override'])
