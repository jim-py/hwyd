from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection, models
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from hwyd.models import Activities, ActivitiesConnection, Settings, CustomFieldsUser


class AdminRelatedLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser('query-admin', '', 'test-only-admin')
        data = dict(user=cls.owner, date='2026-10', color='#111111', backgroundColor='#ffffff',
                    marks='False ' * 31, onOffCells='True ' * 31, number=0, beginDay=0, endDay=30,
                    isOpen=False, cellsComments='', hide=False)
        cls.group = Activities.objects.create(name='Query group', isGroup=True, **data)
        cls.child = Activities.objects.create(name='Query child', isGroup=False, **data)

    def setUp(self):
        self.client.force_login(self.owner)

    def add_rows(self, start, end):
        for i in range(start, end):
            user = get_user_model().objects.create_user(f'query-member-{i:03}')
            ActivitiesConnection.objects.create(user=user, group=self.group, activity=self.child)
            booleans = {field.name: False for field in Settings._meta.fields
                        if isinstance(field, models.BooleanField)}
            Settings.objects.create(user=user, name=f'Query setting {i}', fontFamily='Inter', **booleans)
            CustomFieldsUser.objects.create(user=user, lastActive=timezone.now(), answers='sample')

    def listing(self, model, **params):
        url = reverse(f'admin:hwyd_{model._meta.model_name}_changelist')
        self.client.get(url, params)  # Warm session/content-type caches and first visit.
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        return response, len(queries)

    def test_labels_do_not_add_queries_when_list_grows(self):
        models_to_check = (ActivitiesConnection, Settings, CustomFieldsUser)
        self.add_rows(0, 5)
        small = {}
        for model in models_to_check:
            response, small[model] = self.listing(model)
            self.assertEqual(len(response.context['cl'].result_list), 5)
        self.add_rows(5, 20)
        for model in models_to_check:
            with self.subTest(model=model.__name__):
                response, queries = self.listing(model)
                self.assertEqual(len(response.context['cl'].result_list), 20)
                self.assertContains(response, 'query-member-019')
                self.assertEqual(queries, small[model])

    def test_queryset_and_object_labels_load_relations_in_one_query(self):
        self.add_rows(0, 20)
        request = RequestFactory().get('/admin/')
        request.user = self.owner
        for model in (ActivitiesConnection, Settings, CustomFieldsUser):
            with self.subTest(model=model.__name__), self.assertNumQueries(1):
                objects = list(admin.site._registry[model].get_queryset(request))
                labels = [str(obj) for obj in objects]
                self.assertEqual(len(labels), 20)
                self.assertTrue(all('query-member-' in label for label in labels))

    def test_pagination_keeps_counts_order_and_bounded_queries(self):
        self.add_rows(0, 120)
        for model in (ActivitiesConnection, Settings, CustomFieldsUser):
            with self.subTest(model=model.__name__):
                first, first_queries = self.listing(model, p=1)
                second, second_queries = self.listing(model, p=2)
                changelist = second.context['cl']
                self.assertEqual(changelist.result_count, 120)
                self.assertEqual(len(first.context['cl'].result_list), 100)
                self.assertEqual(len(changelist.result_list), 20)
                self.assertEqual(first_queries, second_queries)
                self.assertEqual(list(changelist.result_list.values_list('pk', flat=True)),
                                 list(model.objects.order_by('-pk').values_list('pk', flat=True))[100:])

    def test_optimized_admin_keeps_view_only_permissions_and_form_relations(self):
        self.add_rows(0, 1)
        staff = get_user_model().objects.create_user('query-reader', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_activitiesconnection'))
        self.client.force_login(staff)
        obj = ActivitiesConnection.objects.get()
        url = reverse('admin:hwyd_activitiesconnection_change', args=[obj.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Query group')
        self.assertContains(response, 'Query child')
        self.assertNotContains(response, 'name="_save"')
        self.assertEqual(self.client.post(url, {'user': self.owner.pk}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:hwyd_settings_changelist')).status_code, 403)
