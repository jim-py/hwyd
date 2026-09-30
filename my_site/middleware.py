import re
from django.conf import settings
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from hwyd.models import UserActivityLog
from django.utils import timezone
from django.db import transaction, IntegrityError
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


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

        tz_name = request.session.get("user_timezone") or "Europe/Moscow"

        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            tz_name = "Europe/Moscow"
            user_tz = ZoneInfo(tz_name)

        now_utc = timezone.now()
        user_local_dt = now_utc.astimezone(user_tz)
        user_local_date = user_local_dt.date()

        try:
            with transaction.atomic():

                log, created = UserActivityLog.objects.get_or_create(
                    user=user,
                    date=user_local_date,
                    defaults={
                        "first_visit": now_utc,
                        "last_visit": now_utc,
                        "timezone": tz_name,
                    }
                )

                if not created:
                    UserActivityLog.objects.filter(pk=log.pk).update(
                        last_visit=now_utc,
                        timezone=tz_name
                    )

        except IntegrityError:
            UserActivityLog.objects.filter(
                user=user,
                date=user_local_date
            ).update(last_visit=now_utc)

        return response


class MaintenanceMiddleware(MiddlewareMixin):
    def __call__(self, request):

        # Проверка на технический перерыв, при этом если он включен пропускать статику
        if getattr(settings, 'MAINTENANCE_MODE', False) and not re.compile(r'^/static/').match(request.path):
            return render(request, 'maintenance.html', status=503)

        response = self.get_response(request)
        return response