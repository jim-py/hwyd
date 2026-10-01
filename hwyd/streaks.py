from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, DateField, Exists, ExpressionWrapper, F, OuterRef, Q, Subquery

from .models import UserActivityLog


def users_with_login_streak():
    """Length of the consecutive visit chain ending at each user's latest log.

    The newest date without a predecessor starts the latest chain. Both
    predecessor lookups and the range count use the existing (user, date) index.
    No visit history or per-user queries are loaded into Python.
    """
    predecessor = UserActivityLog.objects.filter(
        user_id=OuterRef('user_id'),
        date=ExpressionWrapper(OuterRef('date') - timedelta(days=1), output_field=DateField()),
    )
    starts = (UserActivityLog.objects.filter(user_id=OuterRef('pk'))
              .annotate(has_predecessor=Exists(predecessor))
              .filter(has_predecessor=False).order_by('-date').values('date')[:1])
    return get_user_model().objects.annotate(
        streak_start=Subquery(starts),
        login_streak=Count('activity_logs', filter=Q(activity_logs__date__gte=F('streak_start'))),
    )


def streak_position(user):
    streak = users_with_login_streak().filter(pk=user.pk).values_list('login_streak', flat=True).get()
    eligible = users_with_login_streak().filter(is_active=True, login_streak__gt=0)
    rank = 1 + eligible.filter(login_streak__gt=streak).count() if user.is_active and streak else None
    return streak, rank


def streak_top(user):
    streak, rank = streak_position(user)
    leaders = (users_with_login_streak().filter(is_active=True, login_streak__gt=0)
               .order_by('-login_streak', 'username', 'pk')[:10])
    rows = []
    previous_streak = None
    displayed_rank = 0
    for position, leader in enumerate(leaders, 1):
        if leader.login_streak != previous_streak:
            displayed_rank = position
        rows.append({'rank': displayed_rank, 'name': leader.first_name.strip() or leader.username,
                     'streak': leader.login_streak, 'is_own': leader.pk == user.pk})
        previous_streak = leader.login_streak
    return {'leaders': rows, 'current': {'rank': rank, 'streak': streak}}
