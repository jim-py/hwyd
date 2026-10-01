from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Activities, ActivitiesConnection, Feedback, Settings
from .views import create_setting
from .forms import SettingsForm
from .preferences import UI_VISIBILITY_FIELDS
from .models import UserActivityLog
from .streaks import streak_position, streak_top, users_with_login_streak
from datetime import date, timedelta
from django.utils import timezone
from django.test import override_settings


@override_settings(MIDDLEWARE=[
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',
])
class StreakTopTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='current', email='private@example.com')
        self.client.force_login(self.user)

    def visits(self, user, days, end=date(2026, 10, 1)):
        now = timezone.now()
        UserActivityLog.objects.bulk_create([
            UserActivityLog(user=user, date=end - timedelta(days=i), first_visit=now, last_visit=now)
            for i in range(days)])

    def contender(self, username, days, **kwargs):
        user = get_user_model().objects.create_user(username=username, **kwargs)
        self.visits(user, days)
        return user

    def test_current_streak_sorting_ties_names_and_private_fields(self):
        self.visits(self.user, 8)
        self.contender('b', 10, first_name='  Мария  ')
        self.contender('a', 10)
        self.contender('disabled', 50, is_active=False)
        response = self.client.get(reverse('top_streak'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([row['rank'] for row in data['leaders']], [1, 2, 3])
        self.assertEqual([row['name'] for row in data['leaders']], ['a', 'Мария', 'current'])
        self.assertEqual(data['current'], {'rank': 3, 'streak': 8})
        self.assertTrue(data['leaders'][2]['is_own'])
        for row in data['leaders']:
            self.assertEqual(set(row), {'rank', 'name', 'streak', 'is_own'})
        self.assertNotContains(response, 'private@example.com')

    def test_top_ten_and_current_user_outside_top(self):
        for i in range(12):
            self.contender(f'leader-{i:02}', 20 - i)
        self.visits(self.user, 2)
        with self.assertNumQueries(3):
            data = streak_top(self.user)
        self.assertEqual(len(data['leaders']), 10)
        self.assertEqual(data['current'], {'rank': 13, 'streak': 2})
        self.assertFalse(any(row['is_own'] for row in data['leaders']))

    def test_unique_places_and_current_rank_with_tied_streaks(self):
        self.user.username = 'eliasleonheart'
        self.user.first_name = '  Элиас  '
        self.user.save(update_fields=['username', 'first_name'])
        self.visits(self.user, 4)
        for username, days in [('Overcringer', 23), ('Fairfarren', 15),
                               ('knopka_enter', 13), ('ddkk333q', 6), ('аня', 4),
                               ('dmitry', 3), ('Константин', 3), ('mcgregor', 2), ('Дмитрий', 2)]:
            self.contender(username, days, first_name=' \t ')
        with self.assertNumQueries(1):
            data = streak_top(self.user)
        self.assertEqual([row['rank'] for row in data['leaders']], list(range(1, 11)))
        self.assertEqual([row['name'] for row in data['leaders']],
                         ['Overcringer', 'Fairfarren', 'knopka_enter', 'ddkk333q',
                          'Элиас', 'аня', 'dmitry', 'Константин', 'mcgregor', 'Дмитрий'])
        self.assertEqual(data['current'], {'rank': 5, 'streak': 4})
        self.assertTrue(data['leaders'][4]['is_own'])
        for leader in get_user_model().objects.all():
            with self.subTest(username=leader.username):
                own_data = streak_top(leader)
                own_row = next(row for row in own_data['leaders'] if row['is_own'])
                self.assertEqual(own_data['current']['rank'], own_row['rank'])
        create_setting(self.user, 'Test')
        response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
        self.assertContains(response, 'id="topLeaders" class="streak-top" role="list"')

    def test_latest_chain_keeps_original_metric_and_ignores_old_record(self):
        self.visits(self.user, 40, end=date(2026, 8, 1))
        self.visits(self.user, 3, end=date(2026, 9, 20))
        latest = UserActivityLog.objects.filter(user=self.user).latest('date')
        self.assertEqual(latest.get_login_streak(), 3)
        self.assertEqual(streak_position(self.user), (3, 1))
        # As before, the latest chain remains until a new visit after a gap.
        self.visits(self.user, 1)
        self.assertEqual(latest.get_login_streak(), 1)

    def test_hidden_top_does_not_calculate_global_rank(self):
        self.visits(self.user, 5)
        with self.assertNumQueries(1):
            self.assertEqual(streak_position(self.user, include_rank=False), (5, None))

    def test_sql_chain_matches_original_date_algorithm_across_months_and_gaps(self):
        import random
        generator = random.Random(42)
        expected = {}
        for i in range(20):
            user = get_user_model().objects.create_user(username=f'sample-{i}')
            offsets = sorted(generator.sample(range(90), 40))
            now = timezone.now()
            dates = [date(2026, 3, 10) - timedelta(days=offset) for offset in offsets]
            UserActivityLog.objects.bulk_create([UserActivityLog(user=user, date=day, first_visit=now, last_visit=now) for day in dates])
            streak = 1
            for previous, current in zip(dates, dates[1:]):
                if previous - current != timedelta(days=1):
                    break
                streak += 1
            expected[user.pk] = streak
        with self.assertNumQueries(1):
            actual = dict(users_with_login_streak().filter(pk__in=expected).values_list('pk', 'login_streak'))
        self.assertEqual(actual, expected)

    def test_empty_streak_and_authentication(self):
        self.assertEqual(streak_top(self.user), {'leaders': [], 'current': {'rank': None, 'streak': 0}})
        self.assertEqual(self.client.post(reverse('top_streak')).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('top_streak')).status_code, 302)

    def test_toolbar_uses_same_streak_and_replay_is_always_available(self):
        create_setting(self.user, 'Test')
        self.visits(self.user, 6)
        response = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
        self.assertEqual(response.context['login_streak'], 6)
        self.assertEqual(response.context['top_rank'], 1)
        self.assertContains(response, 'fa-trophy')
        self.assertContains(response, 'id="restartGuide"')
        self.assertContains(response, 'hwyd/js/onboarding-loader.js')


class ToolbarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='toolbar-user')
        cls.other = get_user_model().objects.create_user(username='toolbar-other')
        create_setting(cls.user, 'Toolbar')
        Settings.objects.filter(user=cls.user).update(vanishing='off')

    def setUp(self):
        self.client.force_login(self.user)

    def activity(self, name, user=None, month='2026-10', group=False, collapsed=False):
        return Activities.objects.create(
            user=user or self.user, name=name, date=month, color='#000000',
            backgroundColor='#ffffff', marks='False ' * 31, number=0,
            isGroup=group, isOpen=collapsed, beginDay=0, endDay=30,
            cellsComments='*|' * 31, onOffCells='True ' * 31, hide=False)

    def test_feedback_persists_categories_text_and_session_user(self):
        for category in Feedback.Category.values:
            with self.subTest(category=category):
                response = self.client.post(reverse('submit_feedback'), {
                    'category': category, 'message': '  Текст <script>alert(1)</script> 👋  ',
                    'user': self.other.pk})
                self.assertEqual(response.status_code, 201)
                record = Feedback.objects.get(pk=response.json()['id'])
                self.assertEqual(record.user, self.user)
                self.assertEqual(record.message, 'Текст <script>alert(1)</script> 👋')
                self.assertEqual(record.category, category)
                self.assertIsNotNone(record.created_at)

    def test_feedback_rejects_blank_long_and_invalid_category(self):
        for payload in ({'category': 'bug', 'message': ''},
                        {'category': 'bug', 'message': ' \n\t '},
                        {'category': 'bug', 'message': 'a' * 3001},
                        {'category': 'unknown', 'message': 'Text'}):
            with self.subTest(payload=payload['category']):
                self.assertEqual(self.client.post(reverse('submit_feedback'), payload).status_code, 400)
        self.assertFalse(Feedback.objects.exists())

    def test_feedback_requires_authentication_and_post(self):
        self.assertEqual(self.client.get(reverse('submit_feedback')).status_code, 405)
        self.client.logout()
        response = self.client.post(reverse('submit_feedback'), {'category': 'bug', 'message': 'Text'})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Feedback.objects.exists())

    def test_feedback_and_clear_keep_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        url = reverse('submit_feedback')
        data = {'category': 'idea', 'message': 'Test suggestion'}
        self.assertEqual(client.post(url, data).status_code, 403)
        activity = self.activity('Keep until confirmed')
        clear_url = reverse('delete_all', args=['2026-10'])
        self.assertEqual(client.post(clear_url).status_code, 403)
        self.assertTrue(Activities.objects.filter(pk=activity.pk).exists())
        client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post(url, data, HTTP_X_CSRFTOKEN=token).status_code, 201)
        self.assertEqual(client.post(clear_url, HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_feedback_admin_escapes_user_content(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])
        record = Feedback.objects.create(user=self.user, category='bug', message='<script>test</script>')
        response = self.client.get(reverse('admin:hwyd_feedback_change', args=[record.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '&lt;script&gt;test&lt;/script&gt;')
        self.assertNotContains(response, '<script>test</script>')

    def test_group_state_is_persisted_with_owner_and_type_checks(self):
        group = self.activity('Group', group=True, collapsed=True)
        url = reverse('open_group')
        response = self.client.post(url, {'openedGroup': group.pk, 'collapsed': 'false'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['collapsed'])
        group.refresh_from_db()
        self.assertFalse(group.isOpen)
        self.assertEqual(self.client.post(url, {'openedGroup': group.pk}).status_code, 200)
        group.refresh_from_db()
        self.assertTrue(group.isOpen)
        foreign = self.activity('Other group', user=self.other, group=True, collapsed=True)
        habit = self.activity('Habit')
        for target in (foreign, habit):
            self.assertEqual(self.client.post(url, {'openedGroup': target.pk}).status_code, 404)
        self.assertEqual(self.client.post(url, {'openedGroup': 'bad'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'openedGroup': group.pk, 'collapsed': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)
        foreign.refresh_from_db()
        self.assertTrue(foreign.isOpen)

    def test_open_all_toggles_only_own_month_groups(self):
        a = self.activity('A', group=True, collapsed=True)
        b = self.activity('B', group=True)
        foreign = self.activity('Foreign', user=self.other, group=True, collapsed=True)
        previous = self.activity('Previous', month='2026-09', group=True, collapsed=True)
        habit = self.activity('Completed')
        habit.marks = 'True ' * 31
        habit.save(update_fields=['marks'])
        url = reverse('open_all', args=['2026-10'])
        for collapsed in (False, True):
            response = self.client.post(url)
            self.assertEqual(response.status_code, 200)
            for group in (a, b):
                group.refresh_from_db()
                self.assertEqual(group.isOpen, collapsed)
        self.client.post(url, {'collapsed': 'false'})
        a.refresh_from_db()
        self.assertFalse(a.isOpen)
        for untouched in (foreign, previous):
            untouched.refresh_from_db()
            self.assertTrue(untouched.isOpen)
        habit.refresh_from_db()
        self.assertEqual(habit.marks, 'True ' * 31)
        self.assertEqual(self.client.post(url, {'collapsed': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_clear_removes_only_own_month_habits_groups_and_connections(self):
        group = self.activity('Group', group=True)
        habit = self.activity('Habit')
        ActivitiesConnection.objects.create(user=self.user, group=group, activity=habit)
        foreign = self.activity('Foreign', user=self.other)
        previous = self.activity('Previous', month='2026-09')
        url = reverse('delete_all', args=['2026-10'])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(Activities.objects.filter(pk=habit.pk).exists())
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertFalse(Activities.objects.filter(user=self.user, date='2026-10').exists())
        self.assertFalse(ActivitiesConnection.objects.exists())
        self.assertTrue(Activities.objects.filter(pk__in=[foreign.pk, previous.pk]).count() == 2)

    def test_creation_and_month_post_contracts_are_preserved(self):
        for group, field, name in ((0, 'createActivityInput', 'Read'), (1, 'createActivityGroupInput', 'Health')):
            response = self.client.post(reverse('create_activity', args=['2026-10', group]), {field: name})
            self.assertRedirects(response, reverse('by_date', args=['2026-10']), fetch_redirect_response=False)
            self.assertEqual(Activities.objects.get(name=name).isGroup, bool(group))
        for month in ('2020-01', '2030-12'):
            response = self.client.post(reverse('by_date', args=['2026-10']), {'chooseDate': month}, HTTP_HOST='testserver')
            self.assertRedirects(response, reverse('by_date', args=[month]), fetch_redirect_response=False)


class SettingsInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='interface-user')
        cls.other = get_user_model().objects.create_user(username='interface-other')
        create_setting(cls.user, 'Interface')
        create_setting(cls.other, 'Other')

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse('by_date', args=['2026-10'])
        self.client.defaults['HTTP_HOST'] = 'testserver'

    def settings_payload(self):
        return {'data': ','.join(['true'] * 10), 'nameSetting': 'Interface',
                'radioSettings': 'group', 'selectFont': 'Georgia', 'selectFade': 'off',
                'uiVisibilityVersion': '3'}

    def test_new_visibility_defaults_preserve_existing_interface(self):
        preset = Settings.objects.get(user=self.user)
        for name in UI_VISIBILITY_FIELDS:
            with self.subTest(field=name):
                self.assertTrue(getattr(preset, name))
                self.assertTrue(Settings._meta.get_field(name).default)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="buttonSettings"', count=1)
        self.assertContains(response, 'Элементы интерфейса')
        self.assertContains(response, 'Поведение и отображение')

    def test_visibility_persists_off_and_on_through_existing_save(self):
        for enabled in (False, True):
            payload = self.settings_payload()
            if enabled:
                payload.update({name: 'on' for name in UI_VISIBILITY_FIELDS})
            self.assertEqual(self.client.post(self.url, payload).status_code, 302)
            preset = Settings.objects.get(user=self.user)
            for name in UI_VISIBILITY_FIELDS:
                self.assertEqual(getattr(preset, name), enabled)
            self.assertEqual(preset.fontFamily, 'Georgia')
            self.assertEqual(preset.vanishing, 'off')
            self.assertEqual(self.client.get(self.url).status_code, 200)
        foreign = Settings.objects.get(user=self.other)
        self.assertTrue(all(getattr(foreign, name) for name in UI_VISIBILITY_FIELDS))
        self.assertEqual(foreign.fontFamily, 'Inter')

    def test_legacy_save_does_not_reset_new_preferences(self):
        Settings.objects.filter(user=self.user).update(**{name: False for name in UI_VISIBILITY_FIELDS})
        payload = self.settings_payload()
        del payload['uiVisibilityVersion']
        self.client.post(self.url, payload)
        preset = Settings.objects.get(user=self.user)
        self.assertTrue(all(not getattr(preset, name) for name in UI_VISIBILITY_FIELDS))

    def test_version_one_clients_preserve_top_visibility(self):
        for enabled in (False, True):
            Settings.objects.filter(user=self.user).update(showTop=enabled)
            payload = self.settings_payload()
            payload['uiVisibilityVersion'] = '1'
            self.client.post(self.url, payload)
            self.assertEqual(Settings.objects.get(user=self.user).showTop, enabled)

    def test_older_clients_preserve_view_switch_visibility(self):
        for version in ('1', '2'):
            for enabled in (False, True):
                with self.subTest(version=version, enabled=enabled):
                    Settings.objects.filter(user=self.user).update(showViewSwitch=enabled)
                    payload = self.settings_payload()
                    payload['uiVisibilityVersion'] = version
                    self.client.post(self.url, payload)
                    self.assertEqual(Settings.objects.get(user=self.user).showViewSwitch, enabled)

    def test_view_switch_off_uses_table_even_with_calendar_in_url(self):
        payload = self.settings_payload()
        payload.update({name: 'on' for name in UI_VISIBILITY_FIELDS if name != 'showViewSwitch'})
        self.client.post(self.url, payload)
        response = self.client.get(self.url, {'view': 'year', 'year': '2024'})
        self.assertFalse(Settings.objects.get(user=self.user).showViewSwitch)
        for fragment in ('id="trackerViewSwitch"', 'id="trackerYearView"', 'hwyd/js/year-calendar.js'):
            self.assertNotContains(response, fragment)
        self.assertContains(response, 'id="trackerTableView"')
        self.assertContains(response, 'id="myTable"')
        self.assertContains(response, 'Показывать переключатель «Таблица / Год»')
        payload['showViewSwitch'] = 'on'
        self.client.post(self.url, payload)
        self.assertContains(self.client.get(self.url), 'id="trackerViewSwitch"')

    def test_separate_settings_page_saves_toggle_and_preserves_it_for_old_clients(self):
        from django.forms.models import model_to_dict

        for enabled in (False, True):
            preset = Settings.objects.get(user=self.user)
            payload = model_to_dict(preset)
            payload['vanishing'] = 'none'
            payload['uiVisibilityVersion'] = '3'
            if enabled:
                payload['showViewSwitch'] = 'on'
            else:
                payload.pop('showViewSwitch')
            self.assertEqual(self.client.post(reverse('edit_settings'), payload).status_code, 302)
            self.assertEqual(Settings.objects.get(user=self.user).showViewSwitch, enabled)
            payload.pop('uiVisibilityVersion')
            payload.pop('showViewSwitch', None)
            self.client.post(reverse('edit_settings'), payload)
            self.assertEqual(Settings.objects.get(user=self.user).showViewSwitch, enabled)

    def test_top_button_visibility_is_independent_and_survives_reload(self):
        payload = self.settings_payload()
        payload.update({name: 'on' for name in UI_VISIBILITY_FIELDS if name != 'showTop'})
        self.client.post(self.url, payload)
        response = self.client.get(self.url)
        self.assertContains(response, 'id="topStreak" type="button" hidden')
        self.assertNotContains(response, 'id="loginStreak" type="button" hidden')
        self.assertContains(response, 'Показывать кнопку топа')
        self.assertEqual(self.client.get(reverse('top_streak')).status_code, 200)
        payload['showTop'] = 'on'
        self.client.post(self.url, payload)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'id="topStreak" type="button" hidden')

    def test_hidden_controls_keep_chat_feedback_and_completed_state(self):
        Settings.objects.filter(user=self.user).update(
            **{name: False for name in UI_VISIBILITY_FIELDS}, vanishing='off')
        activity = Activities.objects.create(
            user=self.user, name='Visible completed habit', date='2026-10',
            color='#000000', backgroundColor='#ffffff', marks='True ' * 31,
            number=0, isGroup=False, isOpen=False, beginDay=0, endDay=30,
            cellsComments='*|' * 31, onOffCells='True ' * 31, hide=False)
        response = self.client.get(self.url)
        for name in ('buttonChat', 'buttonFeedback', 'hideCompleteActivities', 'loginStreak', 'topStreak'):
            self.assertContains(response, f'id="{name}" type="button" hidden')
        self.assertNotContains(response, 'class="activity-name-icon"')
        self.assertContains(response, 'data-hide-completed="false"')
        self.assertContains(response, 'id="chatDialog"')
        self.assertEqual(self.client.get(reverse('chat:messages')).status_code, 200)
        self.assertEqual(self.client.post(reverse('submit_feedback'), {
            'category': 'idea', 'message': 'Available with hidden button'}).status_code, 201)
        activity.refresh_from_db()
        self.assertEqual(activity.marks, 'True ' * 31)

    def test_navbar_settings_only_on_tracker_and_fonts_on_shared_pages(self):
        Settings.objects.filter(user=self.user).update(fontFamily='Courier New')
        response = self.client.get(self.url)
        navbar = response.content.decode().split('<nav class="nav-menu">')[1].split('</nav>')[0]
        self.assertIn('id="buttonSettings"', navbar)
        for name in ('home', 'about', 'profile', 'edit_settings'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'id="buttonSettings"')
                self.assertContains(response, "--app-font-family: 'Courier New', sans-serif")
        self.client.logout()
        self.assertContains(self.client.get(reverse('entry')), "--app-font-family: 'Montserrat', sans-serif")

    def test_invalid_saved_font_cannot_become_css(self):
        Settings.objects.filter(user=self.user).update(fontFamily="'; color: red; /*")
        self.assertContains(self.client.get(reverse('profile')), "--app-font-family: 'Inter', sans-serif")
        payload = self.settings_payload()
        payload['selectFont'] = "'; color: red; /*"
        Settings.objects.filter(user=self.user).update(fontFamily='Arial')
        self.client.post(self.url, payload)
        self.assertEqual(Settings.objects.get(user=self.user).fontFamily, 'Arial')

    def test_settings_form_updates_all_new_preferences(self):
        from django.forms.models import model_to_dict

        preset = Settings.objects.get(user=self.user)
        data = model_to_dict(preset)
        data['vanishing'] = 'none'
        for name in UI_VISIBILITY_FIELDS:
            data.pop(name)
        form = SettingsForm(data, instance=preset)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        preset.refresh_from_db()
        self.assertTrue(all(not getattr(preset, name) for name in UI_VISIBILITY_FIELDS))

    def test_redundant_closes_removed_and_header_closes_retained(self):
        html = self.client.get(self.url).content.decode()
        for dialog_id, label in (
            ('some-modal-id', 'Закрыть настройки'), ('dialogHead', 'Закрыть настройки цвета'),
            ('dialogCell', 'Закрыть текст клетки'),
        ):
            dialog = html.split(f'id="{dialog_id}"')[1].split('</dialog>')[0]
            self.assertIn(f'aria-label="{label}"', dialog)
            self.assertNotIn('>Закрыть</button>', dialog)
            self.assertIn('Сохранить', dialog)
