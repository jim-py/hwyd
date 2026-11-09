import json
from datetime import date, datetime, timezone
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .ai_service import (SYSTEM, NoRedirect, SummaryServiceError, generate_summary,
                         request_body, retry_seconds, structured_text)
from .habit_summary import monthly_snapshot
from .models import Activities

AI_SETTINGS = dict(AI_SERVICE_BASE_URL='https://api.productivumtesting.ru',
                   AI_SERVICE_KEY='local-test-key', AI_SERVICE_TIMEOUT='120', AI_SUMMARY_MAX_TOKENS='200',
                   AI_SUMMARY_MESSAGE_BYTES='2048')
NOW = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)


class SnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('summary-owner')
        cls.other = get_user_model().objects.create_user('summary-other')

    def habit(self, **overrides):
        values = dict(user=self.user, name='Прогулка 🌳', date='2026-10', number=1,
                      isGroup=False, beginDay=0, endDay=30, hide=False, isOpen=False,
                      color='#000000', backgroundColor='#ffffff', cellsComments='PRIVATE COMMENT',
                      description='PRIVATE DESCRIPTION', marks='True ' * 31, onOffCells='True ' * 31)
        values.update(overrides)
        return Activities.objects.create(**values)

    def snapshot(self, month='2026-10', today=date(2026, 10, 4)):
        return monthly_snapshot(self.user, month, today)

    def test_intervals_enabled_days_groups_hidden_and_owner(self):
        self.habit(beginDay=1, endDay=4, onOffCells='True True False True True')
        self.habit(hide=True, beginDay=0, endDay=0, marks='False')
        self.habit(isGroup=True)
        self.habit(user=self.other)
        self.habit(date='2026-09')
        stats, habits = self.snapshot()
        self.assertEqual((stats['habit_count'], stats['completed'], stats['available'], stats['percent']),
                         (2, 2, 3, 66.7))
        self.assertNotIn('PRIVATE', json.dumps(habits))

    def test_future_month_and_disabled_days_have_no_percentage(self):
        self.habit()
        stats, _ = self.snapshot(today=date(2026, 9, 30))
        self.assertEqual((stats['available'], stats['percent'], stats['through']), (0, None, None))
        Activities.objects.update(onOffCells='False ' * 31)
        self.assertIsNone(self.snapshot()[0]['percent'])

    def test_month_boundary_leap_year_short_and_legacy_arrays(self):
        self.habit(date='2024-02', endDay=99, beginDay=-2)
        stats, _ = self.snapshot('2024-02', date(2026, 11, 1))
        self.assertEqual((stats['completed'], stats['available'], stats['through']), (29, 29, '2024-02-29'))
        Activities.objects.update(onOffCells='True True False', marks='True')
        stats, _ = self.snapshot('2024-02')
        self.assertEqual((stats['completed'], stats['available']), (1, 2))

    def test_snapshot_changes_with_marks_names_availability_and_local_day(self):
        habit = self.habit()
        previous = self.snapshot()[0]['snapshot']
        for field, value in [('marks', 'False ' * 31), ('name', 'Новое имя'), ('endDay', 2)]:
            setattr(habit, field, value)
            habit.save()
            current = self.snapshot()[0]['snapshot']
            self.assertNotEqual(previous, current)
            previous = current
        self.assertNotEqual(previous, self.snapshot(today=date(2026, 10, 5))[0]['snapshot'])

    def test_individual_stats_use_the_same_totals_and_do_not_compare_short_periods(self):
        self.habit(beginDay=1, endDay=3, marks='True True True True', onOffCells='True True False True')
        stats, habits = self.snapshot()
        self.assertEqual((habits[0]['completed'], habits[0]['available'], habits[0]['percent']), (2, 2, 100))
        self.assertEqual(stats['habits'], habits)
        self.assertIsNone(stats['comparison_period'])
        self.assertIsNone(habits[0]['comparison'])
        self.assertEqual(stats['regularity'], {'most_regular': [], 'least_regular': []})

    def test_weekly_improvements_declines_and_actual_period_are_deterministic(self):
        self.habit(name='Чтение', marks='False ' * 7 + 'True ' * 24)
        self.habit(name='Прогулка', marks='True ' * 7 + 'False ' * 24)
        stats, habits = self.snapshot(today=date(2026, 10, 14))
        self.assertEqual(stats['completed'], 14)
        self.assertEqual(stats['available'], 28)
        self.assertEqual(habits[0]['comparison']['delta_pp'], 100)
        self.assertEqual(habits[1]['comparison']['delta_pp'], -100)
        self.assertEqual(stats['changes']['improvements'][0]['name'], 'Чтение')
        self.assertEqual(stats['changes']['declines'][0]['name'], 'Прогулка')
        self.assertEqual(stats['comparison_period'], dict(previous_start='2026-10-01', previous_end='2026-10-07',
                         current_start='2026-10-08', current_end='2026-10-14', compared_count=2))

    def test_disabled_weekdays_never_increase_weekly_denominator(self):
        self.habit(onOffCells=('True ' * 5 + 'False ' * 2) * 2,
                   marks='True ' * 7 + 'True ' * 3 + 'False ' * 4)
        stats, habits = self.snapshot(today=date(2026, 10, 14))
        comparison = habits[0]['comparison']
        self.assertEqual((stats['completed'], stats['available']), (8, 10))
        self.assertEqual((comparison['previous_percent'], comparison['current_percent'], comparison['delta_pp']),
                         (100, 60, -40))

    def test_changed_schedule_begin_and_end_make_weeks_incomparable(self):
        self.habit(name='Новое расписание', onOffCells='False ' + 'True ' * 30)
        self.habit(name='Началась позже', beginDay=7)
        self.habit(name='Завершилась раньше', endDay=6)
        stats, habits = self.snapshot(today=date(2026, 10, 14))
        self.assertTrue(all(habit['comparison'] is None for habit in habits))
        self.assertEqual(stats['comparison_period']['compared_count'], 0)
        self.assertEqual(stats['changes'], {'improvements': [], 'declines': []})

    def test_full_month_compares_only_last_two_weeks_and_deleted_habits_are_absent(self):
        self.habit(marks='False ' * 24 + 'True ' * 7)
        removed = self.habit()
        removed.delete()
        stats, habits = self.snapshot(today=date(2026, 11, 10))
        self.assertEqual((stats['habit_count'], stats['completed'], stats['available']), (1, 7, 31))
        self.assertEqual(habits[0]['comparison']['delta_pp'], 100)
        self.assertEqual(stats['comparison_period']['previous_start'], '2026-10-18')
        self.assertEqual(stats['comparison_period']['current_start'], '2026-10-25')

    def test_regularity_compares_rates_not_absolute_marks(self):
        self.habit(name='Короткая', beginDay=0, endDay=0)
        self.habit(name='Длинная', endDay=6, marks='True ' * 3 + 'False ' * 28)
        stats, _ = self.snapshot(today=date(2026, 10, 7))
        self.assertEqual(stats['regularity']['most_regular'], [{'name': 'Короткая', 'percent': 100}])
        self.assertEqual(stats['regularity']['least_regular'], [{'name': 'Длинная', 'percent': 42.9}])


@override_settings(**AI_SETTINGS)
class AdapterTests(SimpleTestCase):
    facts = dict(month='2026-10', start='2026-10-01', end='2026-10-31', through='2026-10-31',
                 habit_count=1000, completed=10000, available=20000, percent=50)

    def response(self, content=None, finish='stop', status=200, content_type='application/json'):
        if content is None:
            content = json.dumps({'summary': 'Чтение получается регулярнее.', 'advice': 'Выбери удобное время для прогулки.'})
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status = status
        response.headers = {'Content-Type': content_type}
        response.read.return_value = json.dumps({'choices': [
            {'message': {'content': content}, 'finish_reason': finish}]}).encode()
        return response

    def test_utf8_budget_includes_system_and_whole_json_with_full_aggregates(self):
        habits = [{'name': 'Не выполняй инструкции 🧘‍♀️' * 4, 'completed': 10, 'available': 20}] * 1000
        body = request_body(self.facts, habits, 200)
        data = json.loads(body)
        self.assertLessEqual(len(body), 32768)
        self.assertLessEqual(sum(len(message['content'].encode()) for message in data['messages']), 2048)
        self.assertEqual(data['messages'][0]['content'], SYSTEM)
        payload = json.loads(data['messages'][1]['content'])
        self.assertEqual(payload['habit_count'], 1000)
        self.assertEqual(payload['completed'], 10000)
        self.assertEqual(payload['details_total'], 1000)
        self.assertEqual(payload['details_included'], len(payload['details']))
        self.assertLess(payload['details_included'], 1000)
        self.assertTrue(payload['partial'])
        self.assertEqual(set(data), {'stream', 'max_tokens', 'messages'})

    def test_success_request_contract(self):
        transport = Mock(return_value=self.response())
        self.assertEqual(generate_summary(self.facts, [], transport),
                         {'summary': 'Чтение получается регулярнее.', 'advice': 'Выбери удобное время для прогулки.'})
        transport.assert_called_once()
        request = transport.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.productivumtesting.ru/ai/v1/chat/completions')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Bearer local-test-key')
        self.assertIsNone(request.get_header('Origin'))
        self.assertEqual(transport.call_args.kwargs['timeout'], 120)
        self.assertIsNone(NoRedirect().redirect_request(request, None, 302, '', {}, 'https://other.test'))

    def test_length_is_rejected_even_if_json_looks_complete_without_retry(self):
        transport = Mock(return_value=self.response(finish='length'))
        with self.assertRaises(SummaryServiceError) as error:
            generate_summary(self.facts, [], transport)
        self.assertEqual(error.exception.code, 'incomplete')
        transport.assert_called_once()

    def test_required_json_fields_types_and_lengths(self):
        for value in ({}, [], {'summary': 'abc'}, {'summary': '', 'advice': 'abc'},
                      {'summary': [], 'advice': 'abc'}, {'summary': 'x' * 601, 'advice': 'abc'},
                      {'summary': 'abc', 'advice': 'x' * 241}, {'summary': 'abc', 'advice': 'abc', 'extra': 1},
                      {'summary': '<think>internal reasoning', 'advice': 'abc'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                structured_text(json.dumps(value), 'stop')
        self.assertEqual(structured_text('```json\n{"summary":"abc","advice":"def"}\n```', 'stop'),
                         {'summary': 'abc', 'advice': 'def'})

    def test_budget_uses_informative_details_and_configured_contract_cap(self):
        habits = [{'name': f'Обычная {i}', 'completed': 5, 'available': 10} for i in range(30)]
        habits.append({'name': 'Лидер', 'completed': 10, 'available': 10})
        habits.append({'name': 'Редкая', 'completed': 1, 'available': 10})
        body = request_body(self.facts, habits, 200)
        payload = json.loads(json.loads(body)['messages'][1]['content'])
        self.assertEqual(payload['details'][0]['name'], 'Лидер')
        self.assertGreater(payload['details_included'], 0)
        self.assertTrue(payload['partial'])
        for limit in (511, 2049, 'invalid'):
            with override_settings(AI_SUMMARY_MESSAGE_BYTES=limit), self.assertRaises(SummaryServiceError):
                request_body(self.facts, habits, 200)

    def test_missing_or_invalid_configuration_never_calls_transport(self):
        for setting in ({'AI_SERVICE_KEY': ''}, {'AI_SERVICE_TIMEOUT': 'nan'}, {'AI_SERVICE_TIMEOUT': '0'},
                        {'AI_SUMMARY_MAX_TOKENS': 351}, {'AI_SERVICE_BASE_URL': 'https://example.test/?query=1'},
                        {'AI_SERVICE_BASE_URL': 'http://example.test'}):
            transport = Mock()
            with self.subTest(setting=setting), override_settings(**setting), self.assertRaises(SummaryServiceError):
                generate_summary(self.facts, [], transport)
            transport.assert_not_called()

    def test_timeout_and_transport_failure_do_not_retry(self):
        for error in (TimeoutError(), URLError('offline'), ConnectionError()):
            transport = Mock(side_effect=error)
            with self.assertRaises(SummaryServiceError) as raised:
                generate_summary(self.facts, [], transport)
            self.assertEqual(raised.exception.code, 'transport')
            transport.assert_called_once()

    def test_http_statuses_json_or_html_never_expose_upstream_content(self):
        for code in (401, 403, 413, 429, 502, 503, 504, 500, 302):
            for body in (b'<html>secret upstream content</html>', b'{"error":"secret upstream content"}'):
                transport = Mock(side_effect=HTTPError('https://example.test', code, 'error',
                                                       {'Retry-After': '30'}, BytesIO(body)))
                with self.assertRaises(SummaryServiceError) as raised:
                    generate_summary(self.facts, [], transport)
                self.assertNotIn('secret', str(raised.exception))
                if code == 429:
                    self.assertEqual(raised.exception.retry_after, 30)
                transport.assert_called_once()

    def test_retry_after_http_date(self):
        with patch('hwyd.ai_service.datetime') as clock:
            clock.now.return_value = NOW
            self.assertEqual(retry_seconds('Sun, 01 Nov 2026 00:31:00 GMT'), 60)
        self.assertIsNone(retry_seconds('invalid'))

    def test_bad_content_type_empty_malformed_and_oversized_response(self):
        responses = [self.response(content_type='text/html'), self.response(content=''),
                     self.response(content={'text': 'bad'}), self.response(finish='tool_calls')]
        for raw in (b'null', b'{}', b'[]', b'not-json', b'\xff', b'x' * 65537):
            response = self.response()
            response.read.return_value = raw
            responses.append(response)
        for response in responses:
            with self.assertRaises(SummaryServiceError) as raised:
                generate_summary(self.facts, [], Mock(return_value=response))
            self.assertEqual(raised.exception.code, 'invalid_response')


@override_settings(**AI_SETTINGS)
class EndpointTests(SnapshotTests):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user.is_superuser = True
        cls.user.is_staff = True
        cls.user.save(update_fields=['is_superuser', 'is_staff'])

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['user_timezone'] = 'America/Los_Angeles'
        session.save()
        self.url = reverse('habit_summary')
        self.transport = patch('hwyd.ai_service.open_response')
        self.http = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.http.return_value = AdapterTests().response()
        self.clock = patch('hwyd.summary_views.timezone')
        self.clock.start().now.return_value = NOW
        self.addCleanup(self.clock.stop)

    def post(self, **data):
        return self.client.post(self.url, {'month': '2026-10', **data}, content_type='application/json')

    def test_owner_uses_local_date_and_excludes_foreign_data(self):
        self.habit()
        self.habit(user=self.other, name='FOREIGN')
        result = self.post().json()
        self.assertEqual(result['stats']['through'], '2026-10-31')
        self.assertEqual(result['stats']['available'], 31)
        payload = self.http.call_args.args[0].data.decode()
        for excluded in ('FOREIGN', 'PRIVATE', self.user.username):
            self.assertNotIn(excluded, payload)
        self.assertEqual(result['state'], 'success')
        self.assertEqual(set(result['ai']), {'summary', 'advice'})
        self.assertEqual(result['stats']['habits'][0]['percent'], 100)
        self.assertIn(result['ai']['summary'], result['text'])
        result = self.post(month='2026-11').json()
        self.assertEqual(result['state'], 'empty')

    def test_stats_only_work_without_ai_config_and_do_not_call_transport(self):
        self.habit()
        with override_settings(AI_SERVICE_KEY=''):
            response = self.post(generate=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], 'stats')
        self.assertEqual(len(response.json()['stats']['habits']), 1)
        self.assertNotIn('ai', response.json())
        self.http.assert_not_called()

    def test_anonymous_method_and_csrf(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.post().status_code, 401)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(self.url, {'month': '2026-10'}, content_type='application/json').status_code, 403)
        self.http.assert_not_called()

    def test_regular_and_staff_users_have_no_button_and_cannot_request_summary(self):
        for staff in (False, True):
            self.other.is_staff = staff
            self.other.save(update_fields=['is_staff'])
            self.client.force_login(self.other)
            with self.subTest(staff=staff), patch('hwyd.summary_views.monthly_snapshot') as snapshot:
                self.assertEqual(self.post().status_code, 403)
                snapshot.assert_not_called()
                for agent in ('Mozilla/5.0', 'Mozilla/5.0 (iPhone) Mobile Safari/604.1'):
                    response = self.client.get(reverse('by_date', args=['2026-10']),
                                               HTTP_USER_AGENT=agent, HTTP_HOST='testserver')
                    self.assertEqual(response.status_code, 200)
                    self.assertNotContains(response, 'id="habitSummaryButton"')
        self.http.assert_not_called()

    def test_payload_cannot_select_owner_or_supply_totals_url_or_habits(self):
        for extra in ({'userId': self.other.pk}, {'url': 'https://other.test'}, {'percent': 100}, {'habits': []}):
            self.assertEqual(self.post(**extra).status_code, 400)
        for payload in ([], None, {}, {'month': 1}, {'month': '2026-13'}, {'month': '2031-01'},
                        {'month': '2026-1'}, {'month': '2026-10' + 'x' * 1024},
                        {'month': '2026-10', 'generate': 'false'}, {'month': '2026-10', 'generate': 1}):
            self.assertEqual(self.client.post(self.url, json.dumps(payload), content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(self.url, 'broken', content_type='application/json').status_code, 400)
        self.http.assert_not_called()

    def test_preview_rejected_even_with_invalid_target(self):
        admin = get_user_model().objects.create_superuser('summary-admin', password='test')
        self.client.force_login(admin)
        for target in (self.user.pk, 'invalid'):
            self.assertEqual(self.client.post(self.url + f'?view_as={target}', {'month': '2026-10'},
                                             content_type='application/json').status_code, 403)
        self.http.assert_not_called()

    def test_empty_and_zero_denominator_do_not_call_ai(self):
        self.assertEqual(self.post().json()['state'], 'empty')
        self.habit(onOffCells='False ' * 31)
        result = self.post().json()
        self.assertEqual((result['state'], result['stats']['percent']), ('no_days', None))
        self.habit(date='2026-11')
        result = self.post(month='2026-11').json()
        self.assertEqual((result['state'], result['stats']['through']), ('no_days', None))
        self.http.assert_not_called()

    def test_timezone_is_required_and_current_day_is_bounded(self):
        self.habit()
        session = self.client.session
        session['user_timezone'] = 'unknown'
        session.save()
        self.assertEqual(self.post().status_code, 409)
        self.http.assert_not_called()
        session['user_timezone'] = 'Pacific/Kiritimati'
        session.save()
        self.habit(date='2026-11')
        self.assertEqual(self.post(month='2026-11').json()['stats']['available'], 1)

    def test_error_keeps_site_statistics_and_retry_after(self):
        self.habit()
        self.http.side_effect = HTTPError('https://example.test', 429, 'error', {'Retry-After': '90'}, BytesIO())
        response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '90')
        self.assertEqual(response.json()['stats']['percent'], 100)
        self.http.assert_called_once()

    def test_missing_configuration_is_unavailable_not_fake_success(self):
        self.habit()
        with override_settings(AI_SERVICE_KEY=''):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['state'], 'unavailable')
        self.assertNotIn('text', response.json())
        self.http.assert_not_called()

    def test_snapshot_changed_during_generation_is_rejected(self):
        habit = self.habit()
        def changed(*args, **kwargs):
            Activities.objects.filter(pk=habit.pk).update(marks='False ' * 31)
            return AdapterTests().response()
        self.http.side_effect = changed
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['state'], 'stale')
        self.assertNotIn('text', response.json())

    def test_desktop_mobile_render_without_ai_request(self):
        for agent in ('Mozilla/5.0', 'Mozilla/5.0 (iPhone) Mobile Safari/604.1'):
            response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_USER_AGENT=agent, HTTP_HOST='testserver')
            self.assertContains(response, 'aria-label="Сводка привычек"')
            self.assertContains(response, 'id="habitSummaryModal"', count=1)
            self.assertNotContains(response, 'local-test-key')
        self.http.assert_not_called()
