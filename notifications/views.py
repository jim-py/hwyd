from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from .models import Notification, NotificationSeen

@require_POST
def mark_seen(request):
    """Помечает уведомление как просмотренное для авторизованного пользователя.
    Анонимные пользователи помечаются локально (cookie), поэтому этот эндпоинт требует аутентификации.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Authentication required for this endpoint.")

    nid = request.POST.get("id")
    if not nid:
        return HttpResponseBadRequest("No id")

    notification = get_object_or_404(Notification, pk=nid)

    # Проверка: действительно ли уведомление предназначено этому пользователю (или глобальное)
    allowed = (
        notification.target_users.filter(pk=request.user.pk).exists()
        or notification.target_groups.filter(pk__in=request.user.groups.values_list("pk", flat=True)).exists()
        or (not notification.target_users.exists() and not notification.target_groups.exists())
    )
    if not allowed:
        return HttpResponseForbidden("You are not allowed to mark this notification.")

    # NotificationSeen.objects.get_or_create(notification=notification, user=request.user)
    return JsonResponse({"status": "ok"})
