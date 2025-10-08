from django.utils import timezone
from django.db.models import Q
from .models import Notification

def unread_notification(request):
    """
    Возвращает одно актуальное непрочитанное уведомление (или None).
    - для авторизованного пользователя: учитываются target_users и target_groups и исключаются уже просмотренные
    - для анонимного: только глобальные уведомления (без target_users/target_groups)
    """
    now = timezone.now()
    qs = Notification.objects.filter(is_active=True).filter(
        Q(start_at__lte=now) | Q(start_at__isnull=True),
        Q(end_at__gte=now) | Q(end_at__isnull=True)
    )

    if request.user.is_authenticated:
        user_groups = request.user.groups.all()
        qs = qs.filter(
            Q(target_users=request.user) |
            Q(target_groups__in=user_groups) |
            (Q(target_users__isnull=True) & Q(target_groups__isnull=True))
        ).distinct()
        qs = qs.exclude(seen_entries__user=request.user)
    else:
        qs = qs.filter(Q(target_users__isnull=True) & Q(target_groups__isnull=True))

    notification = qs.order_by("-created_at").first()
    return {"unread_notification": notification}
