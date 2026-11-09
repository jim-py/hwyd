import json
import re

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .ai_service import SummaryServiceError, generate_summary
from .habit_summary import monthly_snapshot
from .timezones import browser_timezone
from .view_as import preview_read_only
from .year_stats import MIN_YEAR, MAX_YEAR


@never_cache
@require_POST
@preview_read_only
def habit_summary(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Войдите в аккаунт для получения сводки.'}, status=401)
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Сводка привычек доступна только суперпользователю.'}, status=403)
    try:
        if request.content_type != 'application/json' or len(request.body) > 1024:
            raise ValueError
        data = json.loads(request.body)
        if not isinstance(data, dict) or set(data) != {'month'}:
            raise ValueError
        month = data['month']
        if (not isinstance(month, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month)
                or not MIN_YEAR <= int(month[:4]) <= MAX_YEAR):
            raise ValueError
    except (ValueError, UnicodeError):
        return JsonResponse({'error': 'Передайте только выбранный месяц в формате YYYY-MM.'}, status=400)
    tz = browser_timezone(request.session.get('user_timezone'))
    if tz is None:
        return JsonResponse({'error': 'Не удалось определить ваш часовой пояс. Обновите страницу.',
                             'state': 'error'}, status=409)
    facts, habits = monthly_snapshot(request.user, month, timezone.now().astimezone(tz).date())
    result = {'stats': facts, 'state': 'success'}
    if not facts['habit_count']:
        return JsonResponse({**result, 'state': 'empty'})
    if not facts['available']:
        return JsonResponse({**result, 'state': 'no_days'})
    try:
        text, finish = generate_summary(facts, habits)
        result.update(text=text, truncated=finish == 'length', received_at=timezone.now().isoformat())
    except SummaryServiceError as exc:
        result.update(state='unavailable' if exc.code in ('unavailable', 'transport', 'rate_limited') else 'error',
                      error=str(exc), retry_after=exc.retry_after)
        response = JsonResponse(result, status=exc.status)
        if exc.retry_after is not None:
            response['Retry-After'] = str(exc.retry_after)
        return response
    current, _ = monthly_snapshot(request.user, month, timezone.now().astimezone(tz).date())
    if current['snapshot'] != facts['snapshot']:
        return JsonResponse({'state': 'stale', 'error': 'Данные изменились во время генерации. Обновите сводку.'}, status=409)
    return JsonResponse(result)
