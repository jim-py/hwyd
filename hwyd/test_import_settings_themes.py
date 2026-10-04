import argparse
from datetime import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from scripts.import_settings_themes import ImportProblem, build_plan, import_themes, parse_time
from .models import Settings, ScheduledTheme
from .preferences import THEME_COLOR_FIELDS
from .views import create_setting


class ImportSettingsThemesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='import-owner')
        self.other = get_user_model().objects.create_user(username='import-other')
        create_setting(self.user, 'First')
        self.first = Settings.objects.get(user=self.user)
        create_setting(self.user, 'Selected')
        self.second = Settings.objects.filter(user=self.user).latest('pk')
        create_setting(self.user, 'Third')
        self.third = Settings.objects.filter(user=self.user).latest('pk')
        Settings.objects.filter(user=self.user).update(selected=False)
        self.colors = {field: '#abcdef' for field in THEME_COLOR_FIELDS}
        Settings.objects.filter(pk=self.second.pk).update(selected=True, **self.colors)
        create_setting(self.other, 'Other owner')
        self.before = list(Settings.objects.order_by('pk').values())

    def run_import(self, **kwargs):
        return import_themes(output=lambda line: None, **kwargs)

    def test_preview_is_read_only_and_allocates_minutes_per_owner(self):
        result = self.run_import()
        self.assertEqual(result, {'planned': 4, 'created': 0, 'skipped': 0})
        self.assertFalse(ScheduledTheme.objects.exists())
        plan = build_plan(self.user.pk, time(8))
        self.assertEqual([theme.activation_time for _, theme in plan.create], [time(8), time(8, 1), time(8, 2)])
        self.assertEqual([theme.is_enabled for _, theme in plan.create], [False, True, False])
        self.assertEqual(build_plan(self.other.pk, time(8)).create[0][1].activation_time, time(8))

    def test_apply_copies_all_colors_selected_and_keeps_settings_unchanged(self):
        result = self.run_import(apply=True)
        self.assertEqual(result['created'], 4)
        themes = list(ScheduledTheme.objects.filter(user=self.user).order_by('activation_time'))
        self.assertEqual([theme.name for theme in themes], ['First', 'Selected', 'Third'])
        self.assertEqual([theme.active_time for theme in themes], [None, time(8, 1), None])
        self.assertEqual({field: getattr(themes[1], field) for field in THEME_COLOR_FIELDS}, self.colors)
        self.assertEqual(list(Settings.objects.order_by('pk').values()), self.before)

    def test_repeated_run_does_not_duplicate_even_identical_palettes(self):
        self.run_import(apply=True)
        before = list(ScheduledTheme.objects.order_by('pk').values())
        result = self.run_import(apply=True)
        self.assertEqual(result, {'planned': 0, 'created': 0, 'skipped': 4})
        self.assertEqual(list(ScheduledTheme.objects.order_by('pk').values()), before)

    def test_invalid_colors_anywhere_abort_before_writes(self):
        Settings.objects.filter(user=self.other).update(backgroundColor='invalid')
        with self.assertRaisesMessage(ImportProblem, 'backgroundColor'):
            self.run_import(apply=True)
        self.assertFalse(ScheduledTheme.objects.exists())

    def test_existing_active_time_conflict_does_not_overwrite_themes(self):
        existing = ScheduledTheme.objects.create(user=self.user, name='Manual', activation_time=time(8, 1),
                                                  **self.colors)
        with self.assertRaisesMessage(ImportProblem, '08:01'):
            self.run_import(apply=True)
        self.assertEqual(ScheduledTheme.objects.count(), 1)
        self.assertEqual(ScheduledTheme.objects.get().pk, existing.pk)

    def test_matching_snapshot_with_changed_activation_state_is_reported(self):
        self.run_import(apply=True)
        theme = ScheduledTheme.objects.get(user=self.user, name='Selected')
        theme.is_enabled = False
        theme.save()
        with self.assertRaisesMessage(ImportProblem, 'другое состояние активности'):
            self.run_import(apply=True)
        theme.refresh_from_db()
        self.assertFalse(theme.is_enabled)

    def test_owner_filter_and_midnight_wrap(self):
        self.run_import(apply=True, user_ids=[self.user.pk], start_time=time(23, 59))
        self.assertEqual(ScheduledTheme.objects.count(), 3)
        self.assertFalse(ScheduledTheme.objects.filter(user=self.other).exists())
        self.assertEqual(ScheduledTheme.objects.get(name='First').activation_time, time(23, 59))
        self.assertEqual(ScheduledTheme.objects.get(name='Selected').activation_time, time(0))
        self.assertEqual(ScheduledTheme.objects.get(name='Third').activation_time, time(0, 1))

    def test_mysql_bulk_insert_does_not_need_returned_primary_keys(self):
        # MySQL 5.7 does not return IDs from bulk_create. The importer must not use them.
        from django.db.models.query import QuerySet
        original = QuerySet.bulk_create

        def create_without_ids(queryset, objects, **kwargs):
            result = original(queryset, objects, **kwargs)
            for obj in result:
                obj.pk = None
            return result

        with patch.object(QuerySet, 'bulk_create', create_without_ids):
            self.assertEqual(self.run_import(apply=True)['created'], 4)
        self.assertEqual(ScheduledTheme.objects.count(), 4)

    def test_name_and_color_case_handling(self):
        Settings.objects.filter(pk=self.first.pk).update(name='x' * 100, backgroundColor='#AABBCC')
        self.run_import(apply=True)
        theme = ScheduledTheme.objects.get(user=self.user, activation_time=time(8))
        self.assertEqual(len(theme.name), 80)
        theme.backgroundColor = '#aabbcc'
        theme.save()
        self.assertEqual(self.run_import(apply=True)['created'], 0)

    def test_unknown_database_fails_cleanly(self):
        with self.assertRaisesMessage(ImportProblem, 'Неизвестный alias'):
            self.run_import(using='not-configured')

    def test_missing_target_table_stops_before_writes(self):
        from django.db import connection
        with patch.object(connection.introspection, 'table_names', return_value=[Settings._meta.db_table]):
            with self.assertRaisesMessage(ImportProblem, ScheduledTheme._meta.db_table):
                self.run_import(apply=True)
        self.assertFalse(ScheduledTheme.objects.exists())

    def test_time_parser(self):
        self.assertEqual(parse_time('08:01'), time(8, 1))
        for invalid in ('8:00', '24:00', '08:60', '08:00:01'):
            with self.subTest(time=invalid), self.assertRaises(argparse.ArgumentTypeError):
                parse_time(invalid)
