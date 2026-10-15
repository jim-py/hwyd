"""The shared page theme preserves visit history and its staff-only access."""
from datetime import date, datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from general_app.test_public_pages import PageElements
from .models import UserActivityLog


class ActivityUsersPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user('activity-staff', is_staff=True)
        cls.superuser = User.objects.create_user('activity-superuser', is_superuser=True)
        cls.member = User.objects.create_user('activity-member')
        cls.first = User.objects.create_user('visible-user')
        cls.literal_name = '<img src=x onerror=alert(1)>'
        cls.second = User.objects.create_user(cls.literal_name)
        cls.previous = date(2026, 10, 14)
        cls.current = date(2026, 10, 15)

        def log(user, day, first, last, zone):
            return UserActivityLog.objects.create(user=user, date=day,
                first_visit=datetime.fromisoformat(first).replace(tzinfo=timezone.utc),
                last_visit=datetime.fromisoformat(last).replace(tzinfo=timezone.utc), timezone=zone)

        cls.earlier = log(cls.first, cls.previous, '2026-10-14T00:05', '2026-10-14T03:10', 'Asia/Tokyo')
        cls.later = log(cls.second, cls.previous, '2026-10-14T23:15', '2026-10-15T00:25', 'America/Los_Angeles')
        cls.newest = log(cls.first, cls.current, '2026-10-15T01:00', '2026-10-15T02:00', 'Asia/Tokyo')
        for name in ('unbroken0886', 'work'):
            log(User.objects.create_user(name), cls.current, '2026-10-15T03:00', '2026-10-15T05:00', 'UTC')

    def setUp(self):
        self.url = reverse('activity_users')

    def test_access_remains_limited_to_staff_or_superuser(self):
        self.assertEqual(self.url, '/habitus/activityusers/')
        self.assertRedirects(self.client.get(self.url), reverse('entry') + '?next=' + self.url,
                             fetch_redirect_response=False)
        self.client.force_login(self.member)
        for query in ('', '?view_as=' + str(self.staff.pk)):
            response = self.client.get(self.url + query)
            self.assertEqual(response.status_code, 404)
            self.assertNotContains(response, self.first.username, status_code=404)
        for user in (self.staff, self.superuser):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_page_uses_one_shared_theme_and_keeps_accessible_tables(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'general_app/public_base.html')
        self.assertContains(response, 'data-public-theme="auto"')
        self.assertContains(response, 'productivum.publicTheme')
        self.assertNotContains(response, 'id="buttonSettings"')
        elements = PageElements(response)
        for tag in ('main', 'h1', 'nav'):
            self.assertEqual(len(elements.tags(tag)), 1)
        scripts = [s for s in elements.tags('script') if s.get('src')]
        self.assertEqual([s['src'] for s in scripts], ['/static/general_app/js/public-theme.js?v=20261015'])
        self.assertIn('defer', scripts[0])
        styles = [el['href'] for el in elements.tags('link') if el.get('rel') == 'stylesheet']
        self.assertLess(next(i for i, path in enumerate(styles) if '/public.css?' in path),
                        next(i for i, path in enumerate(styles) if '/activity-users.css?' in path))
        self.assertEqual(len(elements.tags('table')), 2)
        regions = [el for _, el in elements.elements if el.get('role') == 'region']
        self.assertEqual(len(regions), 2)
        self.assertTrue(all(el.get('tabindex') == '0' and el.get('aria-labelledby') for el in regions))
        self.assertEqual(len([th for th in elements.tags('th') if th.get('scope') == 'col']), 8)
        self.assertEqual(len([th for th in elements.tags('th') if th.get('scope') == 'row']), 3)

    def test_grouping_order_local_times_exclusions_and_literal_usernames_are_preserved(self):
        self.client.force_login(self.staff)
        before = list(UserActivityLog.objects.order_by('pk').values())
        response = self.client.get(self.url)
        groups = response.context['grouped_data']
        self.assertEqual([group['date'] for group in groups], [self.current, self.previous])
        self.assertEqual([log.pk for log in groups[0]['users']], [self.newest.pk])
        self.assertEqual([log.pk for log in groups[1]['users']], [self.later.pk, self.earlier.pk])
        for local in ('09:05', '12:10', '16:15', '17:25', '10:00', '11:00'):
            self.assertContains(response, local)
        self.assertContains(response, 'Записей: 1')
        self.assertContains(response, 'Записей: 2')
        self.assertContains(response, '&lt;img src=x onerror=alert(1)&gt;')
        self.assertNotContains(response, self.literal_name)
        self.assertNotContains(response, 'unbroken0886')
        self.assertNotContains(response, '>work<')
        self.assertEqual(list(UserActivityLog.objects.order_by('pk').values()), before)

    def test_empty_state_keeps_the_shared_layout_without_fabricated_rows(self):
        UserActivityLog.objects.all().delete()
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['grouped_data'], [])
        self.assertContains(response, 'Пока нет посещений')
        self.assertContains(response, 'data-public-theme="auto"')
        self.assertEqual(len(PageElements(response).tags('table')), 0)
        self.assertFalse(UserActivityLog.objects.exists())
