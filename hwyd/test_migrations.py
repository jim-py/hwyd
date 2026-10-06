from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from .models import Settings
from .views import create_setting


class TopVisibilityMigrationTests(TransactionTestCase):
    def test_existing_preset_is_preserved_and_top_defaults_to_visible(self):
        user = get_user_model().objects.create_user(username='top-migration-user')
        create_setting(user, 'Existing preset')
        preset = Settings.objects.get(user=user)
        executor = MigrationExecutor(connection)
        executor.migrate([('hwyd', '0003_interface_visibility')])
        try:
            old_apps = executor.loader.project_state([('hwyd', '0003_interface_visibility')]).apps
            previous = old_apps.get_model('hwyd', 'Settings').objects.values().get(pk=preset.pk)
        finally:
            MigrationExecutor(connection).migrate([('hwyd', '0008_activities_description')])
        current = Settings.objects.values().get(pk=preset.pk)
        self.assertTrue(current.pop('showTop'))
        self.assertTrue(current.pop('showViewSwitch'))
        self.assertTrue(current.pop('showThemeSchedule'))
        self.assertEqual(current, previous)


class ViewSwitchMigrationTests(TransactionTestCase):
    def test_existing_preset_defaults_to_visible_without_changing_other_settings(self):
        user = get_user_model().objects.create_user(username='view-switch-migration')
        create_setting(user, 'Existing preset')
        preset = Settings.objects.get(user=user)
        Settings.objects.filter(pk=preset.pk).update(showTop=False, showChat=False, showViewSwitch=False)
        executor = MigrationExecutor(connection)
        executor.migrate([('hwyd', '0004_settings_showtop')])
        try:
            old_apps = executor.loader.project_state([('hwyd', '0004_settings_showtop')]).apps
            previous = old_apps.get_model('hwyd', 'Settings').objects.values().get(pk=preset.pk)
        finally:
            MigrationExecutor(connection).migrate([('hwyd', '0008_activities_description')])
        current = Settings.objects.values().get(pk=preset.pk)
        self.assertTrue(current.pop('showViewSwitch'))
        self.assertTrue(current.pop('showThemeSchedule'))
        self.assertEqual(current, previous)


class ThemeScheduleVisibilityMigrationTests(TransactionTestCase):
    def test_existing_preset_defaults_to_visible_without_changing_other_settings(self):
        user = get_user_model().objects.create_user(username='theme-button-migration')
        create_setting(user, 'Existing preset')
        preset = Settings.objects.get(user=user)
        Settings.objects.filter(pk=preset.pk).update(showTop=False, showViewSwitch=False)
        executor = MigrationExecutor(connection)
        executor.migrate([('hwyd', '0006_scheduledtheme_and_more')])
        try:
            old_apps = executor.loader.project_state([('hwyd', '0006_scheduledtheme_and_more')]).apps
            previous = old_apps.get_model('hwyd', 'Settings').objects.values().get(pk=preset.pk)
        finally:
            MigrationExecutor(connection).migrate([('hwyd', '0008_activities_description')])
        current = Settings.objects.values().get(pk=preset.pk)
        self.assertTrue(current.pop('showThemeSchedule'))
        self.assertEqual(current, previous)
