from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import (
    ClockedSchedule, CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule,
)


class ScheduleInlineAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser('inline-admin', '', 'synthetic-only')
        cls.staff = get_user_model().objects.create_user('inline-reader', is_staff=True)
        cls.staff.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_intervalschedule', 'view_periodictask']))
        cls.schedules = [
            ('interval', IntervalSchedule.objects.create(every=5, period='minutes')),
            ('crontab', CrontabSchedule.objects.create(minute='0')),
            ('solar', SolarSchedule.objects.create(event='sunrise', latitude=50, longitude=30)),
            ('clocked', ClockedSchedule.objects.create(clocked_time=timezone.now())),
        ]

    def add_tasks(self, field, schedule, start, end):
        for i in range(start, end):
            PeriodicTask.objects.create(name=f'{field} task {i}', task='synthetic.noop',
                                        one_off=field == 'clocked', **{field: schedule})

    def test_all_schedule_inlines_keep_queries_constant_and_labels_visible(self):
        self.client.force_login(self.owner)
        request = RequestFactory().get('/admin/')
        request.user = self.owner
        for field, schedule in self.schedules:
            with self.subTest(schedule=field):
                url = reverse(f'admin:django_celery_beat_{schedule._meta.model_name}_change', args=[schedule.pk])
                counts = []
                for start, end in [(0, 5), (5, 20)]:
                    self.add_tasks(field, schedule, start, end)
                    self.assertEqual(self.client.get(url).status_code, 200)
                    with CaptureQueriesContext(connection) as queries:
                        response = self.client.get(url)
                    counts.append(len(queries))
                    self.assertContains(response, f'{field} task {end - 1}')
                    self.assertContains(response, 'admin/js/inlines.js')
                    self.assertContains(response, 'site/admin/theme.js', count=1)
                self.assertEqual(counts[0], counts[1])
                inline = admin.site._registry[type(schedule)].get_inline_instances(request, schedule)[0]
                with self.assertNumQueries(1):
                    labels = [str(task) for task in inline.get_queryset(request).filter(**{field: schedule})]
                self.assertEqual(len(labels), 20)
                self.assertTrue(all(label.startswith(f'{field} task ') for label in labels))
                self.assertFalse(inline.has_add_permission(request, schedule))
                self.assertFalse(inline.can_delete)
                self.assertEqual(inline.readonly_fields, ('name', 'task', 'args', 'kwargs'))

    def test_view_only_schedule_staff_has_readonly_inline_and_no_write_access(self):
        field, schedule = self.schedules[0]
        self.add_tasks(field, schedule, 0, 1)
        self.client.force_login(self.staff)
        url = reverse('admin:django_celery_beat_intervalschedule_change', args=[schedule.pk])
        response = self.client.get(url)
        self.assertContains(response, 'interval task 0')
        self.assertNotContains(response, 'name="_save"')
        self.assertNotContains(response, 'class="add-row"')
        self.assertEqual(self.client.post(url, {'every': 10, 'period': 'minutes'}).status_code, 403)
        schedule.refresh_from_db()
        self.assertEqual(schedule.every, 5)
