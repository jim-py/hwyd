from datetime import date
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from general_app.models import Guide, GuideOpening, UserGuideProgress, UserProfile
from hwyd.models import Feedback, Activities, UserActivityLog
from hwyd.admin_statistics import habit_statistics
from my_site.admin_site import HabitRangeForm
from notifications.models import Notification, NotificationSeen


class AdminPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user('admin-panel-owner', password='test-only-admin', is_staff=True, is_superuser=True)
        cls.staff = get_user_model().objects.create_user('restricted-panel-staff', is_staff=True)
        cls.member = get_user_model().objects.create_user('panel-member')
        cls.guide = Guide.objects.create(slug='main_toolbar', title='Главная панель', version=2)
        cls.notice = Notification.objects.create(title='Объявление', message='<strong>Текст</strong>', is_active=False)
        cls.feedback = Feedback.objects.create(category='bug', user=cls.member, message='<script>alert(1)</script>\nВторая строка')

    def setUp(self):
        self.client.force_login(self.owner)

    def grant(self, *codenames):
        self.staff.user_permissions.set(Permission.objects.filter(codename__in=codenames))
        self.client.force_login(self.staff)

    def state(self):
        return {model.__name__: list(model.objects.order_by('pk').values())
                for model in (Notification, NotificationSeen, GuideOpening, UserGuideProgress, UserProfile,
                              Activities, UserActivityLog)}

    def test_dashboard_keeps_standard_models_and_does_not_claim_unread_feedback(self):
        result = self.client.get(reverse('admin:index'))
        self.assertEqual(result.status_code, 200)
        for text in ('Уведомления', 'Обратная связь', 'Гайды обучения', 'Отметки привычек', 'Все разделы'):
            self.assertContains(result, text)
        self.assertContains(result, reverse('admin:auth_user_changelist'))
        self.assertContains(result, reverse('admin:password_change'))
        self.assertContains(result, reverse('admin:logout'))
        self.assertNotContains(result, '<script>alert(1)</script>')

    def test_custom_endpoints_require_staff_and_parent_model_permissions(self):
        urls = [reverse('admin:habit_statistics'), reverse('admin:general_app_guide_preview', args=[self.guide.pk]),
                reverse('admin:general_app_guide_audience', args=[self.guide.pk]),
                reverse('admin:notifications_notification_audience', args=[self.notice.pk]),
                reverse('admin:notifications_notification_object_preview', args=[self.notice.pk])]
        for user, status in ((self.member, 302), (self.staff, 403)):
            self.client.force_login(user)
            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, status)
        self.grant('view_guide')
        self.assertEqual(self.client.get(urls[1]).status_code, 200)
        self.assertEqual(self.client.get(urls[2]).status_code, 200)
        self.assertEqual(self.client.get(urls[0]).status_code, 403)
        index = self.client.get(reverse('admin:index'))
        self.assertContains(index, 'Гайды обучения')
        self.assertNotContains(index, reverse('admin:hwyd_feedback_changelist'))

    def test_notification_preview_saved_and_unsaved_is_read_only_and_protected(self):
        session = self.client.session
        session['user_timezone'] = 'Europe/Moscow'
        session.save()
        before = self.state()
        with patch('notifications.tasks.send_user_notification') as push, patch('notifications.tasks.send_daily_push.delay') as task:
            unsaved = self.client.post(reverse('admin:notifications_notification_preview'),
                                       {'title': '<draft>', 'message': '<b>Ещё не сохранено</b>'})
            saved = self.client.get(reverse('admin:notifications_notification_object_preview', args=[self.notice.pk]))
            preview = self.client.get(reverse('admin:general_app_guide_preview', args=[self.guide.pk]))
            self.assertEqual(unsaved.status_code, 200)
            self.assertIn('&lt;draft&gt;', unsaved.json()['html'])
            self.assertIn('<b>Ещё не сохранено</b>', unsaved.json()['html'])
            for forbidden in ('mark-seen', 'set-timezone', '<script', 'beforeunload'):
                self.assertNotIn(forbidden, unsaved.json()['html'])
            self.assertIn('<strong>Текст</strong>', saved.json()['html'])
            self.assertEqual(preview.status_code, 200)
            push.assert_not_called()
            task.assert_not_called()
        self.assertEqual(before, self.state())
        for response in (unsaved, saved, preview):
            self.assertEqual(response['X-Frame-Options'], 'DENY')
            self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse('admin:notifications_notification_preview')).status_code, 403)

    def test_notification_preview_view_only_and_add_only_permissions(self):
        self.grant('view_notification')
        url = reverse('admin:notifications_notification_object_preview', args=[self.notice.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'message': 'Changed'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:notifications_notification_preview')).status_code, 403)
        self.grant('add_notification')
        self.assertEqual(self.client.post(reverse('admin:notifications_notification_preview'), {'message': 'New'}).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_openings_repeat_versions_and_progress_are_independent(self):
        self.client.force_login(self.member)
        url = reverse('guide_opened', args=[self.guide.slug])
        for _ in range(2):
            self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(GuideOpening.objects.count(), 1)
        self.assertFalse(UserGuideProgress.objects.exists())
        self.guide.version = 3
        self.guide.save(update_fields=['version'])
        self.assertEqual(self.client.post(url).json()['version'], 3)
        self.assertEqual(set(GuideOpening.objects.values_list('version', flat=True)), {2, 3})
        self.assertEqual(self.client.post('/home/guides/main_toolbar/viewed/').status_code, 200)
        self.assertEqual(GuideOpening.objects.count(), 2)
        self.assertEqual(UserGuideProgress.objects.get().version_seen, 3)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(Client().post(url).status_code, 302)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url).status_code, 403)
        self.assertEqual(self.client.post(reverse('guide_opened', args=['unknown'])).status_code, 404)
        self.guide.is_active = False
        self.guide.save(update_fields=['is_active'])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_counts_do_not_multiply_with_audience_progress_or_versions(self):
        users = [self.owner, self.staff, self.member]
        self.notice.target_users.add(*users)
        groups = [Group.objects.create(name=f'panel-group-{i}') for i in range(2)]
        self.notice.target_groups.add(*groups)
        NotificationSeen.objects.bulk_create([NotificationSeen(notification=self.notice, user=user) for user in users])
        GuideOpening.objects.bulk_create([GuideOpening(guide=self.guide, user=user, version=version)
                                         for user in users for version in (1, 2)])
        UserGuideProgress.objects.bulk_create([UserGuideProgress(guide=self.guide, user=user, viewed=True, version_seen=2) for user in users[:2]])
        notice = admin.site._registry[Notification].get_queryset(self.request()).get(pk=self.notice.pk)
        guide = admin.site._registry[Guide].get_queryset(self.request()).get(pk=self.guide.pk)
        self.assertEqual(notice.confirmed_count, 3)
        self.assertEqual((guide.opened_count, guide.confirmed_count), (3, 2))
        self.guide.version = 3
        self.guide.save(update_fields=['version'])
        guide = admin.site._registry[Guide].get_queryset(self.request()).get(pk=self.guide.pk)
        self.assertEqual((guide.opened_count, guide.confirmed_count), (0, 0))

    def request(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/admin/')
        request.user = self.owner
        return request

    def test_long_audience_is_lazy_bounded_paginated_and_escaped(self):
        users = get_user_model().objects.bulk_create([get_user_model()(username=f'panel-viewer-{i:03}') for i in range(65)])
        users[0].username = '<img src=x onerror=alert(1)>'
        users[0].save(update_fields=['username'])
        NotificationSeen.objects.bulk_create([NotificationSeen(user=user, notification=self.notice) for user in users])
        url = reverse('admin:notifications_notification_audience', args=[self.notice.pk])
        sample = self.client.get(url, {'sample': '1'}).json()
        self.assertEqual((len(sample['names']), sample['total']), (10, 65))
        page = self.client.get(url)
        self.assertEqual(len(page.context['page']), 50)
        self.assertContains(page, '&lt;img')
        self.assertNotContains(page, '<img src=x onerror=alert(1)>')
        self.assertEqual(len(self.client.get(url, {'page': 2}).context['page']), 15)
        self.assertEqual(self.client.get(url, {'q': 'viewer-060'}).context['page'].paginator.count, 1)
        listing = self.client.get(reverse('admin:notifications_notification_changelist'))
        self.assertNotContains(listing, 'panel-viewer-060')

    def test_feedback_safe_full_text_search_filter_and_deleted_author(self):
        url = reverse('admin:hwyd_feedback_change', args=[self.feedback.pk])
        response = self.client.get(url)
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, 'Вторая строка')
        self.member.delete()
        listing = self.client.get(reverse('admin:hwyd_feedback_changelist'), {'q': 'Вторая', 'category__exact': 'bug'})
        self.assertContains(listing, 'Пользователь удалён / не указан')

    def test_unknown_guide_preview_does_not_load_arbitrary_module(self):
        guide = Guide.objects.create(slug='not-shipped', title='Нет модуля')
        result = self.client.get(reverse('admin:general_app_guide_preview', args=[guide.pk]))
        self.assertContains(result, 'нет проверенного модуля')
        self.assertNotContains(result, 'site/admin/guide-preview.js')

    def test_changelist_query_count_does_not_grow_per_row(self):
        for model, url, make in (
            (Notification, reverse('admin:notifications_notification_changelist'), lambda i: Notification(title=f'Notice {i}', message='Hi')),
            (Guide, reverse('admin:general_app_guide_changelist'), lambda i: Guide(title=f'Guide {i}', slug=f'guide-{i}')),
            (Feedback, reverse('admin:hwyd_feedback_changelist'), lambda i: Feedback(category='other', user=self.owner, message=f'Feedback {i}')),
        ):
            self.client.get(url)
            with CaptureQueriesContext(connection) as small:
                self.client.get(url)
            model.objects.bulk_create([make(i) for i in range(20)])
            with CaptureQueriesContext(connection) as large:
                self.client.get(url)
            self.assertLessEqual(len(large), len(small) + 1, model.__name__)


class HabitAdminStatisticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('stats-user')
        cls.other = get_user_model().objects.create_user('stats-other')

    def habit(self, month='2024-02', user=None, group=False, marks='True True False', enabled='True True True', **changes):
        data = dict(user=user or self.user, name='Habit', date=month, backgroundColor='#ffffff', color='#000000',
                    marks=marks, onOffCells=enabled, number=1, isGroup=group, beginDay=0, endDay=2,
                    isOpen=False, cellsComments='', hide=False)
        data.update(changes)
        return Activities.objects.create(**data)

    def test_daily_totals_distinct_users_disabled_cells_groups_and_zero_days(self):
        self.habit()
        self.habit(marks='True True True', enabled='True False True', hide=True)
        self.habit(user=self.other, marks='False True False')
        self.habit(group=True, marks='True True True')
        result = habit_statistics(date(2024, 2, 1), date(2024, 2, 4))
        self.assertEqual([(x['marks'], x['users']) for x in result['days']], [(2, 1), (2, 2), (1, 1), (0, 0)])
        self.assertEqual((result['marks'], result['users'], result['malformed']), (5, 2, 0))

    def test_leap_day_month_boundary_day_bounds_and_bounded_query(self):
        self.habit(marks='False ' * 28 + 'True True True', enabled='True ' * 31, beginDay=28, endDay=30)
        self.habit(month='2024-03', marks='True True True', beginDay=1, endDay=2)
        self.habit(month='2025-02', marks='True ' * 31, enabled='True ' * 31)
        with CaptureQueriesContext(connection) as queries:
            result = habit_statistics(date(2024, 2, 28), date(2024, 3, 2))
        self.assertEqual([(x['marks'], x['users']) for x in result['days']], [(0, 0), (1, 1), (0, 0), (1, 1)])
        self.assertEqual(result['users'], 1)
        self.assertEqual(len(queries), 1)
        self.habit(month='2026-02', marks='True ' * 31, enabled='True ' * 31, endDay=30)
        self.assertEqual(len(habit_statistics(date(2026, 2, 1), date(2026, 2, 28))['days']), 28)

    def test_bad_rows_are_reported_and_excluded_instead_of_silent_zero(self):
        self.habit(marks='True broken True')
        self.habit(enabled='True')
        self.habit(month='2024-02bad')
        self.habit(beginDay=-1)
        self.habit()
        result = habit_statistics(date(2024, 2, 1), date(2024, 3, 1))
        self.assertEqual((result['malformed'], result['marks']), (4, 2))

    def test_empty_period_and_range_validation(self):
        result = habit_statistics(date(2024, 1, 1), date(2024, 1, 2))
        self.assertEqual((result['marks'], result['users']), (0, 0))
        for start, end, valid in [('2024-01-01', '2024-12-31', True), ('2024-01-01', '2025-01-01', False),
                                  ('2024-02-30', '2024-03-01', False), ('2024-03-02', '2024-03-01', False)]:
            self.assertEqual(HabitRangeForm({'start': start, 'end': end}).is_valid(), valid)


class GuideOpeningMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_existing_data_without_inventing_openings(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('general_app', '0003_alter_userprofile_avatar')])
        try:
            old = executor.loader.project_state([('general_app', '0003_alter_userprofile_avatar')]).apps
            user = old.get_model('auth', 'User').objects.create(username='opening-migration-user')
            guide = old.get_model('general_app', 'Guide').objects.create(slug='main_toolbar', title='Old', version=7)
            old.get_model('general_app', 'UserGuideProgress').objects.create(user_id=user.pk, guide_id=guide.pk, viewed=True, version_seen=6)
            old.get_model('general_app', 'UserProfile').objects.create(user_id=user.pk, avatar='profiles/old.png')
        finally:
            MigrationExecutor(connection).migrate([('general_app', '0004_guideopening')])
        self.assertFalse(GuideOpening.objects.exists())
        self.assertEqual(Guide.objects.get(pk=guide.pk).version, 7)
        self.assertEqual(UserGuideProgress.objects.get().version_seen, 6)
        self.assertEqual(UserProfile.objects.get().avatar.name, 'profiles/old.png')
        GuideOpening.objects.create(user_id=user.pk, guide_id=guide.pk, version=7)
        with self.assertRaises(IntegrityError), transaction.atomic():
            GuideOpening.objects.create(user_id=user.pk, guide_id=guide.pk, version=7)
