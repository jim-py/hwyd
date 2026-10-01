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
            MigrationExecutor(connection).migrate([('hwyd', '0004_settings_showtop')])
        current = Settings.objects.values().get(pk=preset.pk)
        self.assertTrue(current.pop('showTop'))
        self.assertEqual(current, previous)
