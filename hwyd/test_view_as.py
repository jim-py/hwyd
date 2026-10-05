"""Preview ownership, authentication identity, presentation, and write safety."""
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from general_app.models import Guide, UserGuideProgress
from .models import Activities, ActivitiesConnection, ScheduledTheme, Settings, UserActivityLog
from .preferences import THEME_COLOR_DEFAULTS
from .theme_schedule import DISPLAY_COLORS_KEY, DISPLAY_THEME_KEY, MANUAL_THEME_KEY
from .views import create_setting

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)


@override_settings(USE_SCHEDULED_THEME_COLORS=True)
class ViewAsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        model = get_user_model()
        cls.admin = model.objects.create_superuser(username='preview-admin', password='test')
        cls.target = model.objects.create_user(username='preview-target', email='private@example.test')
        cls.other = model.objects.create_user(username='preview-other')
        cls.staff = model.objects.create_user(username='preview-staff', is_staff=True)
        for user in (cls.admin, cls.target, cls.other, cls.staff):
            create_setting(user, 'default')
        Settings.objects.filter(user=cls.admin).update(fontFamily='Arial', showChat=False, showCreateActivity=False)
        Settings.objects.filter(user=cls.target).update(fontFamily='Georgia', showChat=True, showCreateActivity=True,
                                                       showDeleteActivity=True, enableSortTable=True)
        cls.own_habit = cls.habit(cls.admin, 'ADMIN HABIT', False)
        cls.target_habit = cls.habit(cls.target, 'TARGET HABIT', True)
        cls.other_habit = cls.habit(cls.other, 'OTHER HABIT', False)
        cls.group = cls.habit(cls.target, 'TARGET GROUP', False, isGroup=True, number=1000)
        ActivitiesConnection.objects.create(user=cls.target, group=cls.group, activity=cls.target_habit)
        cls.admin_theme = cls.theme(cls.admin, 'ADMIN THEME', '#abcdef')
        cls.target_light = cls.theme(cls.target, 'TARGET LIGHT', '#123456')
        cls.target_dark = cls.theme(cls.target, 'TARGET DARK', '#234567', hour=20)
        UserActivityLog.objects.create(user=cls.target, date=NOW.date(), first_visit=NOW,
                                       last_visit=NOW, timezone='UTC')

    @classmethod
    def habit(cls, user, name, marked, **kwargs):
        values = dict(user=user, name=name, date='2026-10', number=0, isGroup=False,
                      beginDay=0, endDay=30, hide=False, isOpen=False, color='#000000',
                      backgroundColor='#ffffff', marks=('True ' if marked else 'False ') + 'False ' * 30,
                      onOffCells='True ' * 31, cellsComments=f'*{name} comment|' + '*|' * 30)
        values.update(kwargs)
        return Activities.objects.create(**values)

    @classmethod
    def theme(cls, user, name, color, hour=8):
        return ScheduledTheme.objects.create(user=user, name=name, activation_time=time(hour),
                                             **{**THEME_COLOR_DEFAULTS, 'backgroundColor': color})

    def setUp(self):
        self.client.defaults['HTTP_HOST'] = 'testserver'
        self.client.force_login(self.admin)
        self.page = reverse('by_date', args=['2026-10'])
        self.clock = patch('hwyd.theme_schedule.timezone.now', return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def preview(self, target=None, **kwargs):
        return self.client.get(self.page, {'view_as': (target or self.target).pk}, **kwargs)

    def test_selector_is_superuser_only_and_uses_last_login_nulls_last(self):
        model = get_user_model()
        model.objects.filter(pk=self.target.pk).update(last_login=NOW)
        model.objects.filter(pk=self.other.pk).update(last_login=NOW - timedelta(days=2))
        model.objects.filter(pk=self.admin.pk).update(last_login=NOW - timedelta(days=3))
        response = self.client.get(self.page)
        self.assertContains(response, 'id="viewAsUser"')
        self.assertEqual(list(response.context['view_as_users']), [
            (self.target.pk, self.target.get_username()), (self.other.pk, self.other.get_username()),
            (self.admin.pk, self.admin.get_username()), (self.staff.pk, self.staff.get_username()),
        ])
        self.assertNotContains(response, self.target.email)
        self.assertContains(response, 'Мой вид')
        for user in (self.target, self.staff):
            self.client.force_login(user)
            response = self.client.get(self.page)
            self.assertNotContains(response, 'id="viewAsUser"')
            self.assertEqual(response.context['viewed_user'], user)

    def test_target_table_groups_settings_theme_toolbar_and_typography(self):
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TARGET HABIT')
        self.assertContains(response, 'TARGET GROUP')
        self.assertNotContains(response, 'ADMIN HABIT')
        self.assertNotContains(response, 'OTHER HABIT')
        self.assertEqual(response.context['connections'], {self.target_habit.pk: self.group.pk})
        self.assertEqual(response.context['groups_progress'][self.group.pk][0], 100)
        self.assertEqual(response.context['settings'].user, self.target)
        self.assertEqual(response.context['app_font_family'], 'Georgia')
        self.assertEqual(response.context['theme_palette']['backgroundColor'], '#123456')
        self.assertEqual(response.context['theme_schedule_state']['active_id'], self.target_light.pk)
        self.assertContains(response, f'<option value="{self.target.pk}" selected>preview-target</option>')
        self.assertContains(response, 'Только чтение')
        self.assertContains(response, 'id="buttonChat" disabled type="button"')
        self.assertNotContains(response, 'chat/js/chat.js')
        self.assertContains(response, 'aria-label="Удалить TARGET HABIT"')
        self.assertEqual(response.context['login_streak'], 1)
        self.assertIn('no-store', response['Cache-Control'])

    def test_auth_identity_and_actor_theme_session_are_unchanged(self):
        session = self.client.session
        actor_state = {
            'user_timezone': 'Pacific/Honolulu', DISPLAY_THEME_KEY: self.admin_theme.pk,
            DISPLAY_COLORS_KEY: {'backgroundColor': '#abcdef'},
            MANUAL_THEME_KEY: {'theme_id': self.admin_theme.pk, 'expires_at': NOW.timestamp() + 10000},
        }
        session.update(actor_state)
        session.save()
        response = self.preview()
        self.assertEqual(response.wsgi_request.user, self.admin)
        self.assertTrue(response.wsgi_request.user.is_superuser)
        self.assertEqual(response.context['user'], self.admin)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.admin.pk))
        for key, value in actor_state.items():
            self.assertEqual(self.client.session[key], value)
        self.assertEqual(response.context['theme_schedule_state']['timezone'], 'UTC')
        self.assertFalse(response.context['theme_schedule_state']['manual_override'])
        self.assertEqual(UserActivityLog.objects.filter(user=self.target).count(), 1)

    def test_async_reads_use_the_same_owner_and_schedule_algorithm(self):
        query = {'view_as': self.target.pk}
        summary = self.client.get(reverse('year_summary', args=[2026]), query).json()
        self.assertEqual(summary['months'][9]['days'][0], {'completed': 1, 'total': 1})
        comments = self.client.post(reverse('get_comments', args=['2026-10']) + f'?view_as={self.target.pk}',
                                    {'cell': '0-0'})
        self.assertContains(comments, 'TARGET HABIT comment')
        self.assertNotContains(comments, 'ADMIN HABIT')
        export = self.client.get(reverse('export_json'), query)
        self.assertContains(export, 'TARGET HABIT')
        self.assertNotContains(export, 'ADMIN HABIT')
        top = self.client.get(reverse('top_streak'), query).json()
        self.assertEqual(top['current']['streak'], 1)
        self.assertTrue(next(row for row in top['leaders'] if row['name'] == self.target.get_username())['is_own'])
        for hour, expected in ((19, self.target_light), (20, self.target_dark)):
            with patch('hwyd.theme_schedule.timezone.now', return_value=NOW.replace(hour=hour)):
                state = self.client.get(reverse('theme_schedule_list'), query).json()
            self.assertEqual(state['active_id'], expected.pk)
            self.assertEqual(state['colors']['backgroundColor'], expected.backgroundColor)
            self.assertEqual({item['id'] for item in state['themes']}, {self.target_light.pk, self.target_dark.pk})

    def test_regular_and_staff_users_cannot_read_foreign_data_via_query_or_session(self):
        for user in (self.other, self.staff):
            self.client.force_login(user)
            session = self.client.session
            session['view_as'] = self.target.pk
            session.save()
            response = self.preview()
            self.assertEqual(response.context['viewed_user'], user)
            self.assertNotContains(response, 'TARGET HABIT')
            self.assertNotContains(response, 'id="viewAsUser"')
            for name, args in (('theme_schedule_list', []), ('export_json', []), ('year_summary', [2026])):
                read = self.client.get(reverse(name, args=args), {'view_as': self.target.pk})
                self.assertNotContains(read, 'TARGET')
                self.assertNotContains(read, '#123456')
            comments = self.client.post(reverse('get_comments', args=['2026-10']) + f'?view_as={self.target.pk}',
                                        {'cell': '0-0'}) if user == self.other else None
            if comments:
                self.assertNotContains(comments, 'TARGET HABIT')

    def test_invalid_deleted_and_self_targets_return_own_view_without_500(self):
        for value in ('bogus', '-1', '99999999', '9' * 100, str(self.admin.pk), ''):
            with self.subTest(value=value):
                response = self.client.get(self.page, {'view_as': value})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'ADMIN HABIT')
                self.assertNotContains(response, 'TARGET HABIT')
                self.assertFalse(response.context['is_view_as'])

    def test_return_to_own_view_and_preview_do_not_persist_selection(self):
        self.preview()
        response = self.client.get(self.page)
        self.assertContains(response, 'ADMIN HABIT')
        self.assertNotContains(response, 'TARGET HABIT')
        self.assertEqual(response.context['settings'].user, self.admin)
        self.assertEqual(response.context['app_font_family'], 'Arial')
        self.assertEqual(response.context['theme_palette']['backgroundColor'], '#abcdef')
        start = self.client.get(reverse('index'), {'view_as': self.target.pk})
        self.assertIn(f'?view_as={self.target.pk}', start.url)

    def test_empty_target_uses_normal_defaults_without_writing_target(self):
        empty = get_user_model().objects.create_user(username='preview-empty')
        Guide.objects.create(slug='main_toolbar', title='Guide')
        before_settings, before_themes = Settings.objects.count(), ScheduledTheme.objects.count()
        response = self.preview(empty)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['settings'].fontFamily, 'Inter')
        self.assertEqual(response.context['theme_palette'], THEME_COLOR_DEFAULTS)
        self.assertEqual(len(response.context['theme_schedule_state']['themes']), 2)
        self.assertEqual(Settings.objects.count(), before_settings)
        self.assertEqual(ScheduledTheme.objects.count(), before_themes)
        self.assertFalse(UserGuideProgress.objects.filter(user=empty).exists())
        self.assertFalse(UserActivityLog.objects.filter(user=empty).exists())

    def test_preview_mutations_are_blocked_without_changing_actor_or_target(self):
        before_habits = list(Activities.objects.values())
        before_settings = list(Settings.objects.values())
        before_themes = list(ScheduledTheme.objects.values())
        actions = [
            ('by_date', ['2026-10'], 'post', {'cell': '0-0', 'symbols': 'x', 'comment': 'changed'}),
            ('check_cell', ['2026-10'], 'post', {'checkboxToCheck': '0-0'}),
            ('delete_activity', [], 'post', {'pk': self.target_habit.pk}),
            ('delete_all', ['2026-10'], 'post', {}),
            ('create_activity', ['2026-10', 0], 'post', {'createActivityInput': 'changed'}),
            ('create_last_activities', ['2026-10'], 'get', {}),
            ('open_group', [], 'post', {'openedGroup': self.group.pk}),
            ('open_all', ['2026-10'], 'post', {}),
            ('global_colors', ['2026-10'], 'post', {}),
            ('change_setting', [], 'post', {'setting': Settings.objects.get(user=self.target).pk}),
            ('add_setting', [], 'post', {}),
            ('delete_setting', [Settings.objects.get(user=self.target).pk], 'post', {}),
            ('select_setting', [Settings.objects.get(user=self.target).pk], 'get', {}),
            ('edit_settings', [], 'post', {}),
            ('theme_schedule_apply', [], 'post', {}),
            ('theme_schedule_create', [], 'post', {}),
            ('theme_schedule_update', [self.target_light.pk], 'patch', {}),
            ('theme_schedule_delete', [self.target_light.pk], 'delete', {}),
        ]
        for name, args, method, data in actions:
            with self.subTest(endpoint=name):
                url = reverse(name, args=args) + f'?view_as={self.target.pk}'
                response = getattr(self.client, method)(url, data)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(list(Activities.objects.values()), before_habits)
        self.assertEqual(list(Settings.objects.values()), before_settings)
        self.assertEqual(list(ScheduledTheme.objects.values()), before_themes)

    def test_stripping_preview_parameter_does_not_grant_target_ownership(self):
        for actor in (self.admin, self.other):
            self.client.force_login(actor)
            self.assertEqual(self.client.post(reverse('delete_activity'), {'pk': self.target_habit.pk}).status_code, 404)
            self.assertEqual(self.client.post(reverse('open_group'), {'openedGroup': self.group.pk}).status_code, 404)
            self.assertEqual(self.client.patch(reverse('theme_schedule_update', args=[self.target_light.pk]),
                                                '{}', content_type='application/json').status_code, 404)
        self.assertTrue(Activities.objects.filter(pk=self.target_habit.pk).exists())

    def test_normal_mutations_with_forged_target_stay_with_authenticated_owner(self):
        self.client.force_login(self.other)
        before = self.target_habit.marks
        response = self.client.post(reverse('check_cell', args=['2026-10']) + f'?view_as={self.target.pk}',
                                    {'checkboxToCheck': '0-0'})
        self.assertEqual(response.status_code, 200)
        self.other_habit.refresh_from_db()
        self.target_habit.refresh_from_db()
        self.assertTrue(self.other_habit.marks.startswith('True'))
        self.assertEqual(self.target_habit.marks, before)

    def test_mobile_preview_and_form_actions_keep_owner_context(self):
        response = self.preview(HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148')
        self.assertContains(response, 'layout-mobile.css')
        self.assertContains(response, f'action="{self.page}?view_as={self.target.pk}"')
        self.assertContains(response, f'data-view-as="{self.target.pk}"')
        self.assertContains(response, f'data-user="{self.target.pk}"')

    def test_target_content_cannot_break_out_of_bootstrap_script(self):
        name = '</script><script>window.previewInjected=1</script>'
        Activities.objects.filter(pk=self.target_habit.pk).update(name=name, cellsComments='*' + name + '|' + '*|' * 30)
        response = self.preview()
        self.assertNotContains(response, name)
        self.assertContains(response, r'\u003C/script\u003E')
        self.assertEqual(response.context['jsonActivities'][0]['name'], name)

    def test_anonymous_target_requests_do_not_expose_data(self):
        self.client.logout()
        self.assertEqual(self.preview().status_code, 302)
        response = self.client.get(reverse('theme_schedule_list'), {'view_as': self.target.pk})
        self.assertEqual(response.status_code, 401)
        self.assertNotContains(response, 'TARGET', status_code=401)
