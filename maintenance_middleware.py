import re
from django.conf import settings
from django.shortcuts import redirect, render
from django.contrib.auth import authenticate, login
from django.utils.deprecation import MiddlewareMixin


class MaintenanceMiddleware(MiddlewareMixin):
    def __call__(self, request):

        # Проверка на технический перерыв, при этом если он включен пропускать статику
        if getattr(settings, 'MAINTENANCE_MODE', False) and not re.compile(r'^/static/').match(request.path):
            return render(request, 'maintenance.html', status=503)

        response = self.get_response(request)
        return response


class BlockAllPagesWithToggleMiddleware(MiddlewareMixin):
    def process_request(self, request):

        # Проверка на блокировку для тестового сайта
        if getattr(settings, 'BLOCK_ALL_PAGES', False):
            if not hasattr(request, 'user') or not request.user.is_authenticated or not request.user.is_superuser:
                return restricted(request)

        response = self.get_response(request)
        return response


def restricted(request):
    if not getattr(settings, 'BLOCK_ALL_PAGES', False):
        return redirect('home')

    error_message = None
    if request.method == 'POST':
        user = authenticate(username='unbroken0886', password=request.POST.get('password'))

        if user is not None and user.is_superuser:
            login(request, user)
            return redirect('home')
        else:
            error_message = 'Неверный пароль. Попробуйте снова.'
    return render(request, 'pass.html', {'error_message': error_message})
