import random
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from webpush import send_user_notification

from .models import Activities, UserActivityLog, CustomFieldsUser

User = get_user_model()


# ======================================================
# НАСТРОЙКИ / ТЕКСТЫ
# ======================================================

MORNING_MESSAGES = [
    "☀️ Новый день — новый шанс стать лучше",
    "🔥 Маленькие шаги каждый день дают большие результаты",
    "💪 Сегодня отличный день, чтобы не сдаться",
    "🚀 Ты ближе к цели, чем думаешь",
    "🧠 Дисциплина важнее мотивации. И она у тебя есть",
    "🌱 Привычки формируют будущее. Начни сегодня",
    "✨ Не идеально — но стабильно",
    "⏳ Один день может многое изменить",
    "🏁 Начни день с правильного шага",
    "🎯 Фокус на сегодня — остальное подождёт",
    "📈 Прогресс важнее скорости",
    "🔥 Ты уже делаешь больше, чем вчера",
    "🌄 Утро — лучшее время для начала",
    "💡 Маленькая победа сегодня = большая завтра",
    "🛠 Работай над собой, даже когда не хочется",
    "📅 Сегодня — часть твоей серии",
    "🧩 Всё складывается из привычек",
    "🌟 Ты способен на большее",
    "⚡ Сделай сегодня чуть лучше, чем вчера",
    "🏆 Регулярность побеждает мотивацию",
]


# ======================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ======================================================

def send_push(user, title, body, ttl=86400):
    send_user_notification(
        user=user,
        payload={
            "title": title,
            "body": body,
        },
        ttl=ttl,
    )


def user_visited_today(user):
    today = timezone.localdate()
    return UserActivityLog.objects.filter(user=user, date=today).exists()


def get_active_activities(user):
    today = timezone.localdate()
    day = today.day

    return Activities.objects.filter(
        user=user,
        hide=False,
        beginDay__lte=day,
        endDay__gte=day,
    )


def activity_marked_today(activity):
    """
    marks — строка с отметками по дням месяца
    """
    today_day = str(timezone.localdate().day)
    return today_day in (activity.marks or "")


# ======================================================
# CELERY TASKS
# ======================================================

@shared_task
def morning_motivation():
    """
    ☀️ Утренняя мотивация (рандомная фраза)
    Запускать 1 раз в день утром
    """
    for user in User.objects.all():
        send_push(
            user,
            "Доброе утро ☀️",
            random.choice(MORNING_MESSAGES),
            ttl=6 * 60 * 60,  # 6 часов
        )


@shared_task
def daily_habit_reminder():
    """
    🔔 Пользователь сегодня НЕ заходил
    """
    for user in User.objects.all():
        if user_visited_today(user):
            continue

        send_push(
            user,
            "🔔 Напоминание",
            "Ты сегодня ещё не заходил в приложение. Зайди и отметь привычки 👋",
        )


@shared_task
def unfinished_habits_evening():
    """
    🌙 Вечер:
    пользователь заходил, но не отметил привычки
    """
    for user in User.objects.all():

        if not user_visited_today(user):
            continue

        activities = get_active_activities(user)

        if not activities.exists():
            continue

        unfinished = [
            activity for activity in activities
            if not activity_marked_today(activity)
        ]

        if unfinished:
            send_push(
                user,
                "⏳ Привычки ждут",
                f"У тебя осталось {len(unfinished)} привычек без отметки. Закрой день 💪",
            )


@shared_task
def inactive_users_reminder():
    """
    😴 Пользователь не заходил 3+ дня
    """
    threshold = timezone.now() - timedelta(days=3)

    inactive_users = User.objects.filter(
        customfieldsuser__lastActive__lt=threshold
    )

    for user in inactive_users:
        send_push(
            user,
            "👋 Мы скучаем",
            "Ты давно не заходил. Самое время вернуться к привычкам 🚀",
        )


@shared_task
def ping():
    """
    ✅ Проверка Celery
    """
    print("CELERY OK")
    return "pong"
