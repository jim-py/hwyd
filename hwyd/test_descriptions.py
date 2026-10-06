from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from .models import Activities
from .views import create_setting


class HabitDescriptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('descriptions')
        cls.other = get_user_model().objects.create_user('other-description')
        cls.admin = get_user_model().objects.create_superuser('description-admin', password='test')
        for user in (cls.user, cls.other, cls.admin):
            create_setting(user, 'Default')

    def setUp(self):
        self.client.force_login(self.user)
        self.page = reverse('by_date', args=['2026-10'])
        self.client.defaults['HTTP_HOST'] = 'testserver'

    def create(self, name='Habit', description=None, group=False):
        data = {'createActivityGroupInput' if group else 'createActivityInput': name}
        if description is not None:
            data['description'] = description
        return self.client.post(reverse('create_activity', args=['2026-10', int(group)]), data)

    def edit(self, habit, **changes):
        data = {'activityPk': habit.pk, 'activityName': habit.name, 'beginDay': 1, 'endDay': 31,
                'color': habit.color, 'backgroundColor': habit.backgroundColor,
                'onOffCells': habit.onOffCells, 'saveWithColor': 'false'}
        data.update(changes)
        return self.client.post(self.page, data)

    def test_creation_editing_clearing_and_old_clients(self):
        text = 'Первая строка\nКавычки " и * | <текст> 😀'
        self.assertEqual(self.create(description=text).status_code, 302)
        habit = Activities.objects.get(user=self.user, name='Habit')
        self.assertEqual(habit.description, text)
        self.assertEqual(self.edit(habit, description='Изменено\nОписание').status_code, 302)
        habit.refresh_from_db()
        self.assertEqual(habit.description, 'Изменено\nОписание')
        self.assertEqual(self.edit(habit, activityName='Renamed').status_code, 302)
        habit.refresh_from_db()
        self.assertEqual(habit.description, 'Изменено\nОписание')
        self.assertEqual(self.edit(habit, description='').status_code, 302)
        habit.refresh_from_db()
        self.assertEqual(habit.description, '')
        self.assertEqual(self.create(name='Legacy').status_code, 302)
        self.assertEqual(Activities.objects.get(name='Legacy').description, '')

    def test_server_limit_for_creation_and_editing_without_partial_writes(self):
        self.assertEqual(self.create(description='я' * 3000).status_code, 302)
        habit = Activities.objects.get(name='Habit')
        self.assertEqual(len(habit.description), 3000)
        response = self.create(name='Too long', description='я' * 3001)
        self.assertEqual(response.status_code, 400)
        self.assertIn('3000', response.json()['error'])
        self.assertFalse(Activities.objects.filter(name='Too long').exists())
        before = Activities.objects.values().get(pk=habit.pk)
        self.assertEqual(self.edit(habit, description='x' * 3001, activityName='Do not change').status_code, 400)
        self.assertEqual(Activities.objects.values().get(pk=habit.pk), before)
        self.assertEqual(self.edit(habit, description='x' * 3000).status_code, 302)
        self.assertEqual(self.create(name='Line endings', description='x' * 2998 + '\r\n\r\n').status_code, 302)
        self.assertEqual(Activities.objects.get(name='Line endings').description, 'x' * 2998 + '\n\n')
        self.assertEqual(self.create(name='Unicode', description='😀' * 3000).status_code, 302)
        self.assertEqual(self.create(name='Too much Unicode', description='😀' * 3001).status_code, 400)

    def test_groups_ignore_manually_supplied_description_and_form_is_disabled(self):
        self.assertEqual(self.create(name='Group', group=True, description='x' * 3001).status_code, 302)
        group = Activities.objects.get(name='Group')
        self.assertEqual(group.description, '')
        self.assertEqual(self.edit(group, description='Never a group description').status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.description, '')
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        html = render_to_string('hwyd/toolbar_create_dialog.html',
                                {'group_type': 1, 'date': '2026-10', 'request': RequestFactory().get('/')})
        self.assertNotIn('name="description"', html)

    def test_foreign_and_preview_writes_are_forbidden_and_csrf_is_required(self):
        self.create(description='Keep')
        habit = Activities.objects.get(name='Habit')
        self.client.force_login(self.other)
        self.assertEqual(self.edit(habit, description='Foreign').status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.page + f'?view_as={self.user.pk}',
                                         {'activityPk': habit.pk, 'description': 'Preview'}).status_code, 403)
        guarded = Client(enforce_csrf_checks=True, HTTP_HOST='testserver')
        guarded.force_login(self.user)
        self.assertEqual(guarded.post(reverse('create_activity', args=['2026-10', 0]),
                                     {'createActivityInput': 'CSRF', 'description': 'No token'}).status_code, 403)
        self.assertEqual(guarded.post(self.page, {'activityPk': habit.pk, 'description': 'No token'}).status_code, 403)
        habit.refresh_from_db()
        self.assertEqual(habit.description, 'Keep')

    def test_safe_tooltip_and_loading_of_description_on_desktop_and_mobile(self):
        text = '<img src=x onerror="alert(1)">\n</script><script>alert(2)</script>'
        self.create(description=text)
        for agent in ('Mozilla/5.0 Desktop', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile Safari/604.1'):
            response = self.client.get(self.page, HTTP_USER_AGENT=agent)
            self.assertContains(response, 'hasDescription')
            self.assertContains(response, 'data-title="&lt;img src=x onerror=&quot;alert(1)&quot;&gt;')
            self.assertNotContains(response, '<img src=x onerror=')
            self.assertNotContains(response, '<script>alert(2)</script>')
            self.assertEqual(response.context['jsonActivities'][0]['description'], text)
        habit = Activities.objects.get(name='Habit')
        self.edit(habit, description='')
        self.assertNotContains(self.client.get(self.page), 'hasDescription')

    def test_copy_to_next_month_and_export_preserve_habit_metadata(self):
        self.create(description='Скопировать\n* | и переносы')
        self.create(name='Group', group=True, description='Ignore')
        self.assertEqual(self.client.post(reverse('create_last_activities', args=['2026-11'])).status_code, 302)
        self.assertEqual(Activities.objects.get(name='Habit', date='2026-11').description, 'Скопировать\n* | и переносы')
        self.assertEqual(Activities.objects.get(name='Group', date='2026-11').description, '')
        export = self.client.get(reverse('export_json')).json()
        self.assertTrue(export['activities'])
        self.assertTrue(all(item['description'] == 'Скопировать\n* | и переносы' for item in export['activities']))
        self.assertTrue(all('description' not in item for item in export['groups']))


class HabitDescriptionMigrationTests(TransactionTestCase):
    def test_upgrade_existing_rows_defaults_to_empty_without_changing_other_data(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('hwyd', '0007_settings_showthemeschedule')])
        try:
            old = executor.loader.project_state([('hwyd', '0007_settings_showthemeschedule')]).apps
            user = old.get_model('auth', 'User').objects.create(username='description-migration')
            model = old.get_model('hwyd', 'Activities')
            rows = []
            for group in (False, True):
                row = model.objects.create(user_id=user.pk, name=f'Legacy {group}', date='2026-10',
                                           isGroup=group, color='#000000', backgroundColor='#ffffff', marks='False ' * 31,
                                           number=int(group), beginDay=0, endDay=30, isOpen=False, hide=False,
                                           cellsComments='*Note|' * 31, onOffCells='True ' * 31)
                rows.append(model.objects.values().get(pk=row.pk))
        finally:
            MigrationExecutor(connection).migrate([('hwyd', '0008_activities_description')])
        for previous in rows:
            upgraded = Activities.objects.values().get(pk=previous['id'])
            self.assertEqual(upgraded.pop('description'), '')
            self.assertEqual(upgraded, previous)
        # Reapplying the target migration is also a no-op.
        MigrationExecutor(connection).migrate([('hwyd', '0008_activities_description')])
