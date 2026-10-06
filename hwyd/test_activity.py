import json
import sqlite3
from datetime import date, datetime, timedelta, timezone as utc_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import UserActivityLog
from .streaks import streak_position


@override_settings(MIDDLEWARE=[
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'my_site.middleware.UserActivityLoggingMiddleware',
])
class VisitTimezoneTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='local-visits')
        self.client.force_login(self.user)
        self.instant = datetime(2026, 10, 1, 21, 30, tzinfo=utc_timezone.utc)

    def set_zone(self, name):
        session = self.client.session
        session['user_timezone'] = name
        session.save()

    def visit(self, instant=None):
        with patch('my_site.middleware.timezone.now', return_value=instant or self.instant):
            return self.client.get(reverse('home'))

    def test_local_date_depends_on_browser_timezone_not_server_date(self):
        for name, expected in [('America/Los_Angeles', date(2026, 10, 1)),
                               ('Pacific/Kiritimati', date(2026, 10, 2)),
                               ('Pacific/Honolulu', date(2026, 10, 1))]:
            with self.subTest(timezone=name):
                UserActivityLog.objects.all().delete()
                self.set_zone(name)
                self.assertEqual(self.visit().status_code, 200)
                log = UserActivityLog.objects.get(user=self.user)
                self.assertEqual(log.date, expected)
                self.assertEqual(log.timezone, name)
                self.assertEqual(log.first_visit, self.instant)
                self.assertEqual(log.last_visit, self.instant)

    def test_first_page_waits_for_timezone_without_phantom_moscow_day(self):
        self.visit()
        self.assertFalse(UserActivityLog.objects.exists())
        with patch('my_site.middleware.timezone.now', return_value=self.instant):
            response = self.client.post(reverse('set_timezone'),
                                        data=json.dumps({'timezone': 'America/Los_Angeles'}),
                                        content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session['user_timezone'], 'America/Los_Angeles')
        self.assertEqual(list(UserActivityLog.objects.values_list('date', flat=True)),
                         [date(2026, 10, 1)])
        self.visit(self.instant + timedelta(minutes=1))
        self.assertEqual(UserActivityLog.objects.count(), 1)

    def test_invalid_timezone_payload_preserves_previous_timezone(self):
        self.set_zone('Pacific/Honolulu')
        payloads = ['not json', '{}', '[]', 'null',
                    '{"timezone":"Made/Up"}', '{"timezone":"../UTC"}',
                    '{"timezone":23}', '{"timezone":["UTC"]}',
                    json.dumps({'timezone': 'a' * 65})]
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(reverse('set_timezone'), data=payload,
                                            content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.client.session['user_timezone'], 'Pacific/Honolulu')

    def test_invalid_session_timezone_is_not_used_to_guess_a_visit(self):
        for name in ('Made/Up', '', ['UTC']):
            with self.subTest(timezone=name):
                self.set_zone(name)
                self.visit()
                self.assertFalse(UserActivityLog.objects.exists())

    def test_repeat_requests_update_last_visit_once_per_local_day(self):
        self.set_zone('America/Los_Angeles')
        self.visit()
        later = self.instant + timedelta(hours=4)  # UTC date changes, local date does not.
        self.visit(later)
        log = UserActivityLog.objects.get()
        self.assertEqual(log.date, date(2026, 10, 1))
        self.assertEqual(log.first_visit, self.instant)
        self.assertEqual(log.last_visit, later)

    def test_late_request_cannot_move_last_visit_backwards(self):
        self.set_zone('UTC')
        self.visit(self.instant + timedelta(seconds=10))
        self.visit(self.instant)
        self.assertEqual(UserActivityLog.objects.get().last_visit, self.instant + timedelta(seconds=10))

    def test_busy_optional_logging_keeps_successful_response_and_retries_next_visit(self):
        self.set_zone('UTC')
        cause = sqlite3.OperationalError('database is locked')
        cause.sqlite_errorcode = getattr(sqlite3, 'SQLITE_BUSY', 5)
        error = OperationalError('database is locked')
        error.__cause__ = cause
        with patch('my_site.middleware.UserActivityLog.objects.get_or_create', side_effect=error):
            with self.assertLogs('my_site.middleware', level='WARNING'):
                self.assertEqual(self.visit().status_code, 200)
        self.assertFalse(UserActivityLog.objects.exists())
        self.visit()
        self.assertEqual(UserActivityLog.objects.get().date, self.instant.date())

    def test_other_database_errors_are_not_hidden(self):
        self.set_zone('UTC')
        with patch('my_site.middleware.UserActivityLog.objects.get_or_create',
                   side_effect=OperationalError('disk I/O error')):
            with self.assertRaises(OperationalError):
                self.visit()

    def test_legacy_sqlite_lock_without_errorcode_is_optional(self):
        self.set_zone('UTC')
        cause = sqlite3.OperationalError('database is locked')
        error = OperationalError('database is locked')
        error.__cause__ = cause
        with patch('my_site.middleware.UserActivityLog.objects.get_or_create', side_effect=error):
            with self.assertLogs('my_site.middleware', level='WARNING'):
                self.assertEqual(self.visit().status_code, 200)

    def test_extended_busy_code_is_optional_but_other_sqlite_codes_are_not(self):
        self.set_zone('UTC')
        for code, allowed in ((5 | (2 << 8), True), (6, True), (10, False)):
            cause = sqlite3.OperationalError('database is locked')
            cause.sqlite_errorcode = code
            error = OperationalError('database is locked')
            error.__cause__ = cause
            with self.subTest(code=code), patch('my_site.middleware.UserActivityLog.objects.get_or_create', side_effect=error):
                if allowed:
                    with self.assertLogs('my_site.middleware', level='WARNING'):
                        self.assertEqual(self.visit().status_code, 200)
                else:
                    with self.assertRaises(OperationalError):
                        self.visit()

    def test_other_database_backends_do_not_hide_lock_errors(self):
        self.set_zone('UTC')
        cause = sqlite3.OperationalError('database is locked')
        cause.sqlite_errorcode = 5
        error = OperationalError('database is locked')
        error.__cause__ = cause
        with patch('my_site.middleware.connection.vendor', 'mysql'), patch(
            'my_site.middleware.UserActivityLog.objects.get_or_create', side_effect=error
        ):
            with self.assertRaises(OperationalError):
                self.visit()

    def test_local_midnight_starts_next_streak_day(self):
        self.set_zone('Asia/Tokyo')
        self.visit(datetime(2026, 10, 1, 14, 59, tzinfo=utc_timezone.utc))
        self.visit(datetime(2026, 10, 1, 15, 1, tzinfo=utc_timezone.utc))
        self.assertEqual(list(UserActivityLog.objects.order_by('date').values_list('date', flat=True)),
                         [date(2026, 10, 1), date(2026, 10, 2)])
        with patch('hwyd.streaks.timezone.now', return_value=datetime(2026, 10, 1, 15, 1, tzinfo=utc_timezone.utc)):
            self.assertEqual(streak_position(self.user), (2, 1))

    def test_daylight_saving_transition_counts_calendar_days_not_24_hours(self):
        self.set_zone('America/New_York')
        self.visit(datetime(2026, 3, 8, 5, 1, tzinfo=utc_timezone.utc))
        self.visit(datetime(2026, 3, 9, 4, 1, tzinfo=utc_timezone.utc))
        with patch('hwyd.streaks.timezone.now', return_value=datetime(2026, 3, 9, 4, 1, tzinfo=utc_timezone.utc)):
            self.assertEqual(streak_position(self.user), (2, 1))

    def test_anonymous_requests_do_not_create_visits(self):
        self.client.logout()
        self.set_zone('UTC')
        self.visit()
        self.assertFalse(UserActivityLog.objects.exists())
