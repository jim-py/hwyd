from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Activities, ActivitiesConnection, Feedback, Settings
from .views import create_setting


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
