"""Manual delivery to real users. Never run as part of automated verification."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_site.settings")
django.setup()

from django.contrib.auth import get_user_model
from webpush import send_user_notification

User = get_user_model()

def send_test_notification(user):
    payload = {
        "title": "Доброго вечера!",
        "body": "У тебя всё получится, я в тебя верю!"
    }

    send_user_notification(
        user=user,
        payload=payload,
        ttl=1000
    )

if __name__ == "__main__":
    # пример вызова
    user = User.objects.filter(username="thor").first()
    if user:
        send_test_notification(user)
    else:
        print("Пользователи не найдены")
    # пример вызова
    user = User.objects.filter(username="unbroken0886").first()
    if user:
        send_test_notification(user)
    else:
        print("Пользователи не найдены")
