import json
import re
from datetime import timedelta
from functools import wraps

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import ChatMessage, ChatReadState, MESSAGE_MAX_LENGTH


PAGE_SIZE = 50
SEND_COOLDOWN_SECONDS = 2
MAX_REQUEST_BYTES = 12000
MAX_CURSOR = 2 ** 63 - 1


def authenticated(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Войдите на сайт, чтобы пользоваться чатом.'}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


def json_body(request):
    if request.content_type != 'application/json':
        raise ValueError
    if int(request.META.get('CONTENT_LENGTH') or 0) > MAX_REQUEST_BYTES:
        raise ValueError
    body = request.body
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError
    data = json.loads(body.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError
    return data


def valid_cursor(value):
    return type(value) is int and 0 <= value <= MAX_CURSOR


def serialize(message, user):
    return {
        'id': message.pk,
        'sender': message.sender.get_username(),
        'text': message.text,
        'created_at': message.created_at.isoformat(),
        'is_own': message.sender_id == user.pk,
    }


@never_cache
@authenticated
@require_http_methods(['GET', 'POST'])
def messages(request):
    if request.method == 'GET':
        queryset = ChatMessage.objects.select_related('sender')
        after = request.GET.get('after_id')
        if after is None:
            page = list(queryset.order_by('-id')[:PAGE_SIZE])
            page.reverse()
            has_more = False
        else:
            if not re.fullmatch(r'[0-9]{1,19}', after) or not valid_cursor(int(after)):
                return JsonResponse({'error': 'Некорректный курсор сообщений.'}, status=400)
            page = list(queryset.filter(id__gt=int(after)).order_by('id')[:PAGE_SIZE + 1])
            has_more = len(page) > PAGE_SIZE
            page = page[:PAGE_SIZE]
        return JsonResponse({
            'messages': [serialize(message, request.user) for message in page],
            'has_more': has_more,
        })

    try:
        data = json_body(request)
    except (ValueError, UnicodeError):
        return JsonResponse({'error': 'Некорректное сообщение.'}, status=400)
    text = data.get('text')
    if not isinstance(text, str) or not text.strip():
        return JsonResponse({'error': 'Введите текст сообщения.'}, status=400)
    # Check the untrimmed payload as well; invalid Unicode cannot be stored safely.
    if len(text) > MESSAGE_MAX_LENGTH or any(0xD800 <= ord(char) <= 0xDFFF for char in text):
        return JsonResponse({'error': 'Сообщение слишком длинное или содержит некорректный текст.'}, status=400)
    text = text.strip()
    ChatReadState.objects.get_or_create(user=request.user)
    now = timezone.now()
    with transaction.atomic():
        # Conditional UPDATE claims the cooldown across processes, including SQLite.
        claimed = ChatReadState.objects.filter(user=request.user).filter(
            Q(last_sent_at__isnull=True) |
            Q(last_sent_at__lte=now - timedelta(seconds=SEND_COOLDOWN_SECONDS))
        ).update(last_sent_at=now)
        if not claimed:
            response = JsonResponse({'error': 'Подождите пару секунд перед отправкой.'}, status=429)
            response['Retry-After'] = str(SEND_COOLDOWN_SECONDS)
            return response
        message = ChatMessage.objects.create(sender=request.user, text=text)
    return JsonResponse({'message': serialize(message, request.user)}, status=201)


@never_cache
@authenticated
@require_GET
def status(request):
    cursor = ChatReadState.objects.filter(user=request.user).values_list(
        'last_read_message_id', flat=True
    ).first() or 0
    unread = ChatMessage.objects.filter(id__gt=cursor).exclude(sender=request.user).exists()
    return JsonResponse({'has_unread': unread})


@never_cache
@authenticated
@require_POST
def mark_read(request):
    try:
        cursor = json_body(request).get('last_read_message_id')
    except (ValueError, UnicodeError):
        return JsonResponse({'error': 'Некорректный запрос.'}, status=400)
    if not valid_cursor(cursor) or (cursor and not ChatMessage.objects.filter(pk=cursor).exists()):
        return JsonResponse({'error': 'Некорректный курсор сообщений.'}, status=400)
    ChatReadState.objects.get_or_create(user=request.user)
    # Never regress the cursor when another tab sends an older read acknowledgement.
    ChatReadState.objects.filter(user=request.user, last_read_message_id__lt=cursor).update(
        last_read_message_id=cursor
    )
    return JsonResponse({'ok': True})
