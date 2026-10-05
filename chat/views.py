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

from general_app.user_roles import display_role

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


def display_name(user):
    return user.first_name.strip() or user.get_username()


def serialize(message, user):
    target = message.reply_to
    return {
        'id': message.pk,
        'sender': display_name(message.sender),
        'sender_role': display_role(message.sender),
        'sender_id': message.sender_id,
        'text': message.text,
        'created_at': message.created_at.isoformat(),
        'is_own': message.sender_id == user.pk,
        'edited_at': message.edited_at.isoformat() if message.edited_at else None,
        'is_deleted': message.deleted_at is not None,
        'reply_to': {
            'id': target.pk, 'sender': display_name(target.sender),
            'sender_role': display_role(target.sender),
            'text': target.text[:160] if target.deleted_at is None else '',
            # Bounded lookahead lets the client avoid cutting a composed emoji
            # at the 160-codepoint preview boundary. Keep the original API text.
            'preview_text': target.text[:224] if target.deleted_at is None else '',
            'is_deleted': target.deleted_at is not None,
        } if target else None,
    }


def validated_text(data):
    text = data.get('text')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Введите текст сообщения.')
    if len(text) > MESSAGE_MAX_LENGTH or any(0xD800 <= ord(char) <= 0xDFFF for char in text):
        raise ValueError('Сообщение слишком длинное или содержит некорректный текст.')
    return text.strip()


def message_queryset():
    return ChatMessage.objects.select_related('sender', 'reply_to__sender')


@never_cache
@authenticated
@require_http_methods(['GET', 'POST'])
def messages(request):
    if request.method == 'GET':
        queryset = message_queryset().filter(deleted_at__isnull=True)
        refresh = request.GET.get('refresh_ids')
        refresh_ids = []
        if refresh is not None:
            parts = refresh.split(',')
            if len(parts) > PAGE_SIZE or any(
                not re.fullmatch(r'[0-9]{1,19}', part) or not valid_cursor(int(part)) or int(part) == 0
                for part in parts
            ):
                return JsonResponse({'error': 'Некорректные идентификаторы сообщений.'}, status=400)
            refresh_ids = [int(part) for part in parts]
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
            # Bounded reconciliation of loaded messages, including tombstones.
            'updated_messages': [serialize(item, request.user) for item in
                                 message_queryset().filter(pk__in=refresh_ids)],
            'missing_ids': sorted(set(refresh_ids) - set(ChatMessage.objects.filter(
                pk__in=refresh_ids).values_list('pk', flat=True))),
        })

    try:
        data = json_body(request)
    except (ValueError, UnicodeError):
        return JsonResponse({'error': 'Некорректное сообщение.'}, status=400)
    try:
        text = validated_text(data)
    except ValueError as failure:
        return JsonResponse({'error': str(failure)}, status=400)
    reply_id = data.get('reply_to')
    if reply_id is not None and (not valid_cursor(reply_id) or reply_id == 0):
        return JsonResponse({'error': 'Некорректное сообщение для ответа.'}, status=400)
    ChatReadState.objects.get_or_create(user=request.user)
    now = timezone.now()
    with transaction.atomic():
        target = None
        if reply_id is not None:
            target = ChatMessage.objects.select_for_update().filter(pk=reply_id, deleted_at__isnull=True).first()
            if target is None:
                return JsonResponse({'error': 'Сообщение для ответа удалено или не найдено.'}, status=404)
        # Conditional UPDATE claims the cooldown across processes, including SQLite.
        claimed = ChatReadState.objects.filter(user=request.user).filter(
            Q(last_sent_at__isnull=True) |
            Q(last_sent_at__lte=now - timedelta(seconds=SEND_COOLDOWN_SECONDS))
        ).update(last_sent_at=now)
        if not claimed:
            response = JsonResponse({'error': 'Подождите пару секунд перед отправкой.'}, status=429)
            response['Retry-After'] = str(SEND_COOLDOWN_SECONDS)
            return response
        message = ChatMessage.objects.create(sender=request.user, text=text, reply_to=target)
    return JsonResponse({'message': serialize(message, request.user)}, status=201)


@never_cache
@authenticated
@require_GET
def status(request):
    cursor = ChatReadState.objects.filter(user=request.user).values_list(
        'last_read_message_id', flat=True
    ).first() or 0
    unread = ChatMessage.objects.filter(id__gt=cursor, deleted_at__isnull=True).exclude(sender=request.user).exists()
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


@never_cache
@authenticated
@require_http_methods(['PATCH', 'DELETE'])
def message_detail(request, message_id):
    if not valid_cursor(message_id) or message_id == 0:
        return JsonResponse({'error': 'Некорректный идентификатор сообщения.'}, status=400)
    message = message_queryset().filter(pk=message_id).first()
    if message is None:
        return JsonResponse({'error': 'Сообщение удалено или не найдено.'}, status=404)
    if message.sender_id != request.user.pk:
        return JsonResponse({'error': 'Можно изменять и удалять только свои сообщения.'}, status=403)
    if message.deleted_at is not None:
        return JsonResponse({'error': 'Сообщение удалено или не найдено.'}, status=404)
    if request.method == 'PATCH':
        try:
            data = json_body(request)
        except (ValueError, UnicodeError):
            return JsonResponse({'error': 'Некорректное сообщение.'}, status=400)
        try:
            text = validated_text(data)
        except ValueError as failure:
            return JsonResponse({'error': str(failure)}, status=400)
        values = {'text': text, 'edited_at': timezone.now()}
    else:
        values = {'text': '', 'deleted_at': timezone.now()}
    # Include ownership and deletion state in the UPDATE as well as the initial
    # check: an intervening deletion must never be resurrected by an edit.
    changed = ChatMessage.objects.filter(pk=message_id, sender=request.user,
                                         deleted_at__isnull=True).update(**values)
    if not changed:
        return JsonResponse({'error': 'Сообщение удалено или не найдено.'}, status=404)
    return JsonResponse({'message': serialize(message_queryset().get(pk=message_id), request.user)})
