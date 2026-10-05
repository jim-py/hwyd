"""Exercise real concurrent requests against a disposable file-backed SQLite DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, current_thread
from time import sleep
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import JsonResponse
from django.utils import timezone

from chat.models import ChatMessage, ChatReadState
from chat.views import status
from my_site.middleware import UserActivityLoggingMiddleware
from .models import ScheduledTheme, Settings, UserActivityLog
from .preferences import THEME_COLOR_FIELDS, THEME_COLOR_DEFAULTS
from .theme_schedule import schedule_state, ensure_default_themes
from .theme_views import theme_schedule_apply
from .views import create_setting


@skipUnless(connection.vendor == 'sqlite', 'SQLite-specific locking regression')
@override_settings(USE_SCHEDULED_THEME_COLORS=True)
class SQLiteRequestConcurrencyTests(SimpleTestCase):
    databases = {'default'}

    def setUp(self):
        # Preserve the runner's in-memory connection: closing it would discard
        # its schema. Only the temporary file is used by these worker threads.
        connection.ensure_connection()
        self.runner_connection = connection.connection
        self.runner_name = connection.settings_dict['NAME']
        self.temp = TemporaryDirectory(prefix='habitus-concurrency-')
        connection.connection = None
        connection.settings_dict['NAME'] = str(Path(self.temp.name) / 'requests.sqlite3')
        self.addCleanup(self.restore_database)
        with connection.schema_editor() as editor:
            for model in (get_user_model(), Settings, ScheduledTheme, UserActivityLog, ChatMessage, ChatReadState):
                editor.create_model(model)
        self.user = get_user_model().objects.create_user(username='concurrent-owner')
        create_setting(self.user, 'Current')
        self.colors = {field: '#123456' for field in THEME_COLOR_FIELDS}
        ScheduledTheme.objects.create(user=self.user, name='Current theme', activation_time=time(0), **self.colors)

    def restore_database(self):
        connection.close()
        connection.settings_dict['NAME'] = self.runner_name
        connection.connection = self.runner_connection
        self.temp.cleanup()

    def request(self, view, method='post', barrier=None):
        try:
            if barrier:
                barrier.wait(timeout=5)
            request = getattr(RequestFactory(), method)('/test/', data={})
            request.user = self.user
            request.session = {'user_timezone': 'UTC'}
            return UserActivityLoggingMiddleware(view)(request).status_code
        finally:
            connections['default'].close()

    def test_chat_status_can_log_visit_while_theme_writer_is_active(self):
        now = timezone.now()
        UserActivityLog.objects.create(user=self.user, date=now.date(), first_visit=now, last_visit=now, timezone='UTC')
        writer_ready, visit_read = Event(), Event()
        original_get = UserActivityLog.objects.get_or_create

        def get_visit(*args, **kwargs):
            result = original_get(*args, **kwargs)
            if current_thread().name.startswith('chat'):
                visit_read.set()
            return result

        def apply_after_chat_read(*args, **kwargs):
            writer_ready.set()
            if not visit_read.wait(timeout=5):
                raise AssertionError('Chat did not reach visit logging')
            sleep(0.05)  # Keep the writer active when the other request attempts its UPDATE.
            return schedule_state(*args, **kwargs)

        with patch('hwyd.theme_views.schedule_state', side_effect=apply_after_chat_read), \
             patch.object(UserActivityLog.objects, 'get_or_create', side_effect=get_visit), \
             patch('my_site.middleware.logger.warning') as deferred, \
             ThreadPoolExecutor(max_workers=1, thread_name_prefix='theme') as theme_pool, \
             ThreadPoolExecutor(max_workers=1, thread_name_prefix='chat') as chat_pool:
            theme = theme_pool.submit(self.request, theme_schedule_apply)
            self.assertTrue(writer_ready.wait(timeout=5))
            chat = chat_pool.submit(self.request, status, 'get')
            self.assertEqual(theme.result(timeout=10), 200)
            self.assertEqual(chat.result(timeout=10), 200)
            deferred.assert_not_called()
        self.assertEqual(UserActivityLog.objects.count(), 1)
        self.assertEqual(Settings.objects.get(user=self.user).backgroundColor, THEME_COLOR_DEFAULTS['backgroundColor'])

    def test_parallel_theme_apply_and_first_visits_remain_consistent(self):
        barrier = Barrier(4)
        with patch('my_site.middleware.logger.warning') as deferred, ThreadPoolExecutor(max_workers=4) as pool:
            requests = [pool.submit(self.request, theme_schedule_apply, 'post', barrier) for _ in range(4)]
            self.assertEqual([request.result(timeout=10) for request in requests], [200] * 4)
            deferred.assert_not_called()
        self.assertEqual(UserActivityLog.objects.count(), 1)
        self.assertEqual(UserActivityLog.objects.get().timezone, 'UTC')
        preset = Settings.objects.get(user=self.user)
        self.assertEqual({field: getattr(preset, field) for field in THEME_COLOR_FIELDS}, THEME_COLOR_DEFAULTS)


    def test_parallel_empty_scope_bootstrap_creates_exactly_two_themes(self):
        ScheduledTheme.objects.filter(user=self.user).delete()
        barrier = Barrier(4)

        def themed_page(request):
            ensure_default_themes(request.user)
            return JsonResponse(schedule_state(request, apply=True))

        with ThreadPoolExecutor(max_workers=4) as pool:
            requests = [pool.submit(self.request, themed_page, 'get', barrier) for _ in range(4)]
            self.assertEqual([request.result(timeout=10) for request in requests], [200] * 4)
        themes = list(ScheduledTheme.objects.filter(user=self.user))
        self.assertEqual([theme.name for theme in themes], ['Светлая', 'Тёмная'])
        self.assertEqual([theme.activation_time for theme in themes], [time(8), time(20)])
        self.assertEqual(Settings.objects.get(user=self.user).backgroundColor, THEME_COLOR_DEFAULTS['backgroundColor'])
