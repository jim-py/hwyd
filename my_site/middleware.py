import logging
import re
from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED
from django.conf import settings
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from hwyd.models import UserActivityLog
from django.utils import timezone
from django.db import connection, OperationalError
from hwyd.timezones import browser_timezone

logger = logging.getLogger(__name__)


class UserActivityLoggingMiddleware:
    """
    Логирует активность пользователя.

    - UTC хранится в базе
    - date рассчитывается в TZ пользователя
    - timezone сохраняется в запись
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        response = self.get_response(request)

        if not request.user.is_authenticated:
            return response

        user = request.user

        tz_name = request.session.get("user_timezone")
        user_tz = browser_timezone(tz_name)
        if user_tz is None:
            # The first page precedes the browser's timezone POST. Recording a
            # Moscow fallback here could create a second, incorrect visit day.
            return response

        now_utc = timezone.now()
        user_local_dt = now_utc.astimezone(user_tz)
        user_local_date = user_local_dt.date()

        try:
            # Keep the read outside a write transaction. A deferred SQLite
            # read transaction cannot wait when another writer blocks its upgrade.
            # get_or_create already handles the unique (user, date) creation race.
            log, created = UserActivityLog.objects.get_or_create(
                user=user,
                date=user_local_date,
                defaults={"first_visit": now_utc, "last_visit": now_utc, "timezone": tz_name},
            )
            if not created:
                UserActivityLog.objects.filter(pk=log.pk, last_visit__lte=now_utc).update(
                    last_visit=now_utc, timezone=tz_name,
                )
        except OperationalError as exc:
            # Optional bookkeeping must not turn a successful API response into
            # HTTP 500 if an external/long SQLite writer outlasts the busy timeout.
            code = getattr(exc.__cause__, 'sqlite_errorcode', None)
            if connection.vendor != 'sqlite' or code is None or (code & 0xff) not in (SQLITE_BUSY, SQLITE_LOCKED):
                raise
            logger.warning('SQLite visit logging deferred until the next request: database is busy.')

        return response


class MaintenanceMiddleware(MiddlewareMixin):
    def __call__(self, request):

        # Проверка на технический перерыв, при этом если он включен пропускать статику
        if getattr(settings, 'MAINTENANCE_MODE', False) and not re.compile(r'^/static/').match(request.path):
            return render(request, 'maintenance.html', status=503)

        response = self.get_response(request)
        return response
