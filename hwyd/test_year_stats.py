from calendar import monthrange

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Activities
from .views import create_setting
from .year_stats import year_completion


@override_settings(MIDDLEWARE=[
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',
])
class YearCalendarTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='calendar-owner')
        self.other = get_user_model().objects.create_user(username='calendar-other')
        self.client.force_login(self.user)

    def habit(self, *, owner=None, month='2026-01', group=False, begin=0, end=30,
              marks=None, enabled=None, hidden=False):
        return Activities.objects.create(
            user=owner or self.user, name='Habit', date=month, number=1,
            isGroup=group, beginDay=begin, endDay=end, hide=hidden, isOpen=False,
            color='#000000', backgroundColor='#ffffff', cellsComments='',
            marks=marks if marks is not None else 'False ' * 31,
            onOffCells=enabled if enabled is not None else 'True ' * 31,
        )

    def test_daily_counts_respect_enabled_days_limits_groups_and_owner(self):
        self.habit(begin=0, end=2, marks='True True True', enabled='True False True')
        self.habit(begin=1, end=2, marks='True False False')
        self.habit(group=True, marks='True ' * 31)
        self.habit(owner=self.other, marks='True ' * 31)
        self.habit(month='2025-12', marks='True ' * 31)
        self.habit(month='2027-01', marks='True ' * 31)
        with self.assertNumQueries(1):
            result = year_completion(self.user, 2026)
        self.assertEqual(result['months'][0]['days'][:4], [
            {'completed': 1, 'total': 1},
            {'completed': 0, 'total': 1},
            {'completed': 1, 'total': 2},
            {'completed': 0, 'total': 0},
        ])
        self.assertTrue(all(day['total'] == 0 for month in result['months'][1:] for day in month['days']))

    def test_hidden_habits_are_counted_as_data_not_display_preferences(self):
        self.habit(hidden=True, begin=0, end=0, marks='True')
        self.assertEqual(year_completion(self.user, 2026)['months'][0]['days'][0],
                         {'completed': 1, 'total': 1})

    def test_leap_day_and_month_lengths(self):
        self.habit(month='2024-02', marks='True ' * 31)
        self.habit(month='2026-02', marks='True ' * 31)
        leap = year_completion(self.user, 2024)
        regular = year_completion(self.user, 2026)
        self.assertEqual(sum(len(month['days']) for month in leap['months']), 366)
        self.assertEqual(sum(len(month['days']) for month in regular['months']), 365)
        self.assertEqual(len(leap['months'][1]['days']), 29)
        self.assertEqual(len(regular['months'][1]['days']), 28)
        self.assertEqual(leap['months'][1]['days'][28], {'completed': 1, 'total': 1})

    def test_short_legacy_fields_and_bad_months_do_not_break_calendar(self):
        self.habit(enabled='True True False', marks='True', begin=-1, end=100)
        self.habit(month='2026-13', marks='True ' * 31)
        self.habit(month='2026-1x', marks='True ' * 31)
        self.habit(begin=5, end=2, marks='True ' * 31)
        result = year_completion(self.user, 2026)
        self.assertEqual(result['months'][0]['days'][:3], [
            {'completed': 1, 'total': 1}, {'completed': 0, 'total': 1},
            {'completed': 0, 'total': 0},
        ])

    def test_empty_year_and_many_monthly_rows_use_one_query(self):
        with self.assertNumQueries(1):
            empty = year_completion(self.user, 2026)
        self.assertTrue(all(day['total'] == 0 for month in empty['months'] for day in month['days']))
        sample = self.habit()
        rows = []
        for month in range(1, 13):
            for number in range(50):
                row = Activities(**{field.attname: getattr(sample, field.attname)
                                    for field in Activities._meta.fields if not field.primary_key})
                row.date = f'2026-{month:02}'
                row.number = number
                rows.append(row)
        Activities.objects.bulk_create(rows)
        with self.assertNumQueries(1):
            result = year_completion(self.user, 2026)
        for month in range(1, 13):
            self.assertEqual(len(result['months'][month - 1]['days']), monthrange(2026, month)[1])
            self.assertEqual(result['months'][month - 1]['days'][0]['total'], 51 if month == 1 else 50)

    def test_api_returns_only_own_counts_and_is_not_cached(self):
        self.habit(begin=0, end=0, marks='True')
        self.habit(owner=self.other, marks='True ' * 31)
        response = self.client.get(reverse('year_summary', args=[2026]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {'year', 'months'})
        self.assertEqual(data['months'][0]['days'][0], {'completed': 1, 'total': 1})
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotContains(response, 'calendar-other')
        self.assertEqual(self.client.post(reverse('year_summary', args=[2026])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('year_summary', args=[2026])).status_code, 302)

    def test_invalid_years_are_rejected_without_querying_habits(self):
        for year in (2019, 2031, 999999):
            with self.subTest(year=year):
                response = self.client.get(reverse('year_summary', args=[year]))
                self.assertEqual(response.status_code, 400)

    def test_table_page_contains_switch_and_initially_hidden_calendar(self):
        create_setting(self.user, 'Calendar test')
        for agent in ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile Safari/604.1'):
            with self.subTest(agent=agent):
                response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver',
                                           HTTP_USER_AGENT=agent)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="trackerViewSwitch"')
                self.assertContains(response, 'aria-controls="trackerYearView" aria-pressed="false"')
                self.assertContains(response, 'aria-labelledby="yearCalendarTitle" hidden')
                self.assertContains(response, reverse('year_summary', args=[2020]))
                self.assertContains(response, 'id="myTable"')
