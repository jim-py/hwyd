import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .forms import ScheduledThemeForm
from .models import ScheduledTheme
from .theme_schedule import lock_theme_owner, schedule_state, selected_settings, theme_colors


def error(message, status=400):
    return JsonResponse({'success': False, 'error': message}, status=status)


def payload(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError('Некорректный JSON.')
    if not isinstance(data, dict):
        raise ValidationError('Ожидается объект JSON.')
    if 'is_enabled' in data and type(data['is_enabled']) is not bool:
        raise ValidationError('Поле «Активна» должно быть true или false.')
    if 'activation_time' in data and not isinstance(data['activation_time'], str):
        raise ValidationError('Укажите время в формате ЧЧ:ММ.')
    return data


def lock_owner(request):
    lock_theme_owner(request.user.pk)


@never_cache
@require_GET
def theme_schedule_list(request):
    if not request.user.is_authenticated:
        return error('Войдите в аккаунт.', 401)
    return JsonResponse(schedule_state(request))


@never_cache
@require_POST
def theme_schedule_create(request):
    return save_theme(request)


@never_cache
@require_http_methods(['PATCH', 'POST'])
def theme_schedule_update(request, pk):
    return save_theme(request, pk)


def save_theme(request, pk=None):
    if not request.user.is_authenticated:
        return error('Войдите в аккаунт.', 401)
    try:
        data = payload(request)
        with transaction.atomic():
            lock_owner(request)
            if pk is None:
                preset = selected_settings(request.user)
                if preset is None:
                    return error('Сначала выберите настройки интерфейса.', 409)
                theme = ScheduledTheme(user=request.user, **theme_colors(preset, strict=True))
            else:
                theme = ScheduledTheme.objects.filter(pk=pk, user=request.user).first()
                if theme is None:
                    return error('Тема не найдена.', 404)
                if set(data) - {'name', 'activation_time', 'is_enabled'}:
                    return error('Можно изменить только название, время и активность темы.')
            values = {'name': data.get('name', theme.name),
                      'activation_time': data.get('activation_time', theme.activation_time),
                      'is_enabled': data.get('is_enabled', theme.is_enabled)}
            if not isinstance(values['name'], str):
                return error('Введите название темы.')
            # ModelForm's TimeField also accepts datetime.time on partial updates.
            form = ScheduledThemeForm(values, instance=theme)
            if not form.is_valid():
                return error(next(iter(form.errors.values()))[0])
            theme = form.save(commit=False)
            theme.full_clean()
            theme.save()
            state = schedule_state(request, apply=True, force=True)
            state['theme'] = next(item for item in state['themes'] if item['id'] == theme.pk)
            return JsonResponse(state, status=201 if pk is None else 200)
    except ValidationError as exc:
        return error(exc.messages[0])
    except IntegrityError:
        return error('На это время уже назначена другая тема. Обновите список.', 409)


@never_cache
@require_http_methods(['DELETE', 'POST'])
def theme_schedule_delete(request, pk):
    if not request.user.is_authenticated:
        return error('Войдите в аккаунт.', 401)
    with transaction.atomic():
        lock_owner(request)
        theme = ScheduledTheme.objects.filter(pk=pk, user=request.user).first()
        if theme is None:
            return error('Тема не найдена.', 404)
        theme.delete()
        return JsonResponse(schedule_state(request, apply=True, force=True))


@never_cache
@require_POST
def theme_schedule_apply(request):
    if not request.user.is_authenticated:
        return error('Войдите в аккаунт.', 401)
    with transaction.atomic():
        lock_owner(request)
        return JsonResponse(schedule_state(request, apply=True))
