import re
from django.conf import settings
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from datetime import datetime, date
from hwyd.models import UserActivityLog


class UserActivityLoggingMiddleware:
    """
    Middleware для записи активности пользователя каждый раз, когда он делает запрос.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            today = date.today()
            log, created = UserActivityLog.objects.get_or_create(
                user=request.user,
                date=today
            )
            # Если запись уже есть, обновляем last_visit
            if not created:
                log.last_visit = datetime.now()
                log.save()

        return response


class MaintenanceMiddleware(MiddlewareMixin):
    def __call__(self, request):

        # Проверка на технический перерыв, при этом если он включен пропускать статику
        if getattr(settings, 'MAINTENANCE_MODE', False) and not re.compile(r'^/static/').match(request.path):
            return render(request, 'maintenance.html', status=503)

        response = self.get_response(request)
        return response