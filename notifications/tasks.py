from celery import shared_task
from django.contrib.auth import get_user_model
from webpush import send_user_notification

User = get_user_model()

@shared_task
def send_daily_push():
    for user in User.objects.filter(username="thor"):
        send_user_notification(
            user=user,
            payload={
                "title": "Напоминание",
                "body": "Зайди в приложение 👋"
            },
            ttl=86400
        )
    for user in User.objects.filter(username="unbroken0886"):
        send_user_notification(
            user=user,
            payload={
                "title": "Напоминание",
                "body": "Зайди в приложение 👋"
            },
            ttl=86400
        )


@shared_task
def ping():
    print("CELERY OK")
    return 'pong'