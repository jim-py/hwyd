from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from general_app.models import Guide
from notifications.models import Notification


class AdminThemeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser('theme-admin', '', 'test-only-admin')
        cls.staff = get_user_model().objects.create_user('theme-reader', is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(codename='view_notification'))
        cls.guide = Guide.objects.create(slug='main_toolbar', title='Theme guide')
        cls.notice = Notification.objects.create(title='Theme notice', message='Preview text')

    def assert_admin_theme(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'site/admin/theme.js', count=1)
        self.assertContains(response, 'site/admin/admin.css', count=1)
        self.assertContains(response, 'admin/css/dark_mode.css', count=1)
        self.assertNotContains(response, 'admin/js/theme.js')
        self.assertContains(response, 'class="theme-toggle"', count=1)
        for label in ('Системная', 'Светлая', 'Тёмная'):
            self.assertContains(response, label)

    def test_login_and_standard_pages_have_one_keyboard_button_and_theme(self):
        self.assert_admin_theme(Client().get(reverse('admin:login')))
        self.client.force_login(self.owner)
        urls = [reverse('admin:index'), reverse('admin:app_list', args=['notifications']),
                reverse('admin:notifications_notification_changelist'),
                reverse('admin:notifications_notification_add'),
                reverse('admin:notifications_notification_change', args=[self.notice.pk]),
                reverse('admin:notifications_notification_history', args=[self.notice.pk]),
                reverse('admin:notifications_notification_delete', args=[self.notice.pk]),
                reverse('admin:password_change')]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_admin_theme(response)
                self.assertContains(response, '<button type="button" class="theme-toggle"')

    def test_custom_pages_inherit_theme_and_keyboard_scroll_regions(self):
        self.client.force_login(self.owner)
        for url in (reverse('admin:habit_statistics'),
                    reverse('admin:general_app_guide_preview', args=[self.guide.pk]),
                    reverse('admin:general_app_guide_audience', args=[self.guide.pk]),
                    reverse('admin:notifications_notification_audience', args=[self.notice.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_admin_theme(response)
                self.assertContains(response, 'class="pv-table-scroll" tabindex="0" role="region"')

    def test_form_errors_keep_theme_and_standard_widgets(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('admin:notifications_notification_add'),
                                    {'title': 'Invalid dates', 'message': '', 'is_active': 'on'})
        self.assert_admin_theme(response)
        self.assertContains(response, 'errornote')
        for asset in ('admin/js/calendar.js', 'admin/js/admin/DateTimeShortcuts.js',
                      'admin/js/autocomplete.js', 'admin/js/admin/RelatedObjectLookups.js'):
            self.assertContains(response, asset)
        self.assertContains(response, 'admin-autocomplete')
        self.assertEqual(Notification.objects.count(), 1)

    def test_view_only_staff_keeps_permissions_and_fallback_selectors(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:notifications_notification_change', args=[self.notice.pk]))
        self.assert_admin_theme(response)
        self.assertNotContains(response, 'name="_save"')
        self.assertEqual(self.client.post(reverse('admin:notifications_notification_change', args=[self.notice.pk]),
                                          {'title': 'Forbidden'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:general_app_guide_changelist')).status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(codename='add_notification'))
        # No auth User/Group view permission: retain the existing filter selectors.
        response = self.client.get(reverse('admin:notifications_notification_add'))
        self.assertContains(response, 'admin/js/SelectFilter2.js')
        self.assertNotContains(response, 'class="admin-autocomplete"')
        self.assertEqual(self.client.get(reverse('admin:autocomplete'), {
            'app_label': 'notifications', 'model_name': 'notification',
            'field_name': 'target_users', 'term': 'theme',
        }).status_code, 403)

    def test_notification_create_edit_history_and_delete_remain_available(self):
        self.client.force_login(self.owner)
        data = {'title': 'Admin lifecycle', 'message': 'Synthetic content', 'is_active': 'on'}
        self.assertEqual(self.client.post(reverse('admin:notifications_notification_add'), data).status_code, 302)
        obj = Notification.objects.get(title='Admin lifecycle')
        data['title'] = 'Admin lifecycle edited'
        self.assertEqual(self.client.post(reverse('admin:notifications_notification_change', args=[obj.pk]),
                                          data).status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.title, data['title'])
        history = self.client.get(reverse('admin:notifications_notification_history', args=[obj.pk]))
        self.assert_admin_theme(history)
        self.assertEqual(len(history.context['action_list']), 2)
        self.assertEqual(self.client.post(reverse('admin:notifications_notification_delete', args=[obj.pk]),
                                          {'post': 'yes'}).status_code, 302)
        self.assertFalse(Notification.objects.filter(pk=obj.pk).exists())

    def test_bulk_action_keeps_confirmation_and_only_deletes_selection(self):
        self.client.force_login(self.owner)
        selected = Notification.objects.create(title='Selected', message='Synthetic content')
        url = reverse('admin:notifications_notification_changelist')
        data = {'action': 'delete_selected', '_selected_action': [selected.pk]}
        confirmation = self.client.post(url, data)
        self.assert_admin_theme(confirmation)
        self.assertTrue(Notification.objects.filter(pk=selected.pk).exists())
        self.assertEqual(self.client.post(url, {**data, 'post': 'yes'}).status_code, 302)
        self.assertFalse(Notification.objects.filter(pk=selected.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=self.notice.pk).exists())

    def test_public_pages_do_not_receive_admin_resources(self):
        for name in ('home', 'about', 'entry'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'site/admin/theme.js')
                self.assertNotContains(response, 'site/admin/admin.css')
                self.assertNotContains(response, 'theme-toggle')
