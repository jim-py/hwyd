from datetime import timedelta, timezone as utc_timezone

from django.contrib.auth import get_user_model
from django.db.models import Case, DateField, Exists, ExpressionWrapper, F, Func, IntegerField, OuterRef, Q, Subquery, Value, When
from django.utils import timezone

from general_app.user_roles import display_role

from .models import UserActivityLog
from .timezones import browser_timezone


class InclusiveDays(Func):
    """Number of calendar dates between chain start and end, inclusive."""
    function = 'DATEDIFF'
    template = '(%(function)s(%(expressions)s) + 1)'
    output_field = IntegerField()

    def as_sqlite(self, compiler, connection, **extra_context):
        end_sql, end_params = compiler.compile(self.source_expressions[0])
        start_sql, start_params = compiler.compile(self.source_expressions[1])
        return (f'(CAST(julianday({end_sql}) - julianday({start_sql}) AS integer) + 1)',
                [*end_params, *start_params])


def active_streak_days(now):
    """Group recent visit timezones by today's date, without DB timezone tables."""
    utc_today = now.astimezone(utc_timezone.utc).date()
    # Across all timezones, yesterday can be two dates behind the UTC date.
    # Restrict discovery to recent logs; old timezone history cannot be active.
    names = (UserActivityLog.objects.filter(
        date__range=(utc_today - timedelta(days=2), utc_today + timedelta(days=1)))
        .order_by().values_list('timezone', flat=True).distinct())
    days = {}
    for name in names:
        zone = browser_timezone(name)
        if zone is not None:
            days.setdefault(now.astimezone(zone).date(), []).append(name)
    return days


def users_with_login_streak():
    """Length of the ongoing visit chain, or zero if a local day was missed.

    The newest date without a predecessor starts the latest chain. Both
    date lookups use the existing (user, date) index. A chain has no missing
    dates, so its length is end - start + 1. Avoid joining every visit and
    repeating the chain-start subquery per historical visit inside COUNT.
    Only distinct recent timezone names are loaded into Python, in one query.
    Calendar cutoffs use the latest log's timezone, not the viewer's timezone.
    No per-user queries are needed, on SQLite or MySQL.
    """
    days = active_streak_days(timezone.now())
    predecessor = UserActivityLog.objects.filter(
        user_id=OuterRef('user_id'),
        date=ExpressionWrapper(OuterRef('date') - timedelta(days=1), output_field=DateField()),
    )
    starts = (UserActivityLog.objects.filter(user_id=OuterRef('pk'))
              .annotate(has_predecessor=Exists(predecessor))
              .filter(has_predecessor=False).order_by('-date').values('date')[:1])
    latest = UserActivityLog.objects.filter(user_id=OuterRef('pk')).order_by('-date')
    return get_user_model().objects.alias(
        streak_start=Subquery(starts),
        streak_end=Subquery(latest.values('date')[:1]),
        streak_timezone=Subquery(latest.values('timezone')[:1]),
    ).annotate(login_streak=Case(*[
        When(Q(streak_timezone__in=names,
               streak_end__range=(today - timedelta(days=1), today)),
             then=InclusiveDays(F('streak_end'), F('streak_start')))
        for today, names in days.items()
    ], default=Value(0), output_field=IntegerField()))


def streak_position(user, *, include_rank=True):
    return _streak_position(users_with_login_streak(), user, include_rank=include_rank)


def _streak_position(users, user, *, include_rank=True):
    state = users.filter(pk=user.pk).values('login_streak', 'username').get()
    streak = state['login_streak']
    if not include_rank:
        return streak, None
    eligible = users.filter(is_active=True, login_streak__gt=0)
    # Use the same ordering as the leaderboard, including its tie breakers.
    preceding = (Q(login_streak__gt=streak)
                 | Q(login_streak=streak, username__lt=state['username'])
                 | Q(login_streak=streak, username=state['username'], pk__lt=user.pk))
    rank = 1 + eligible.filter(preceding).count() if user.is_active and streak else None
    return streak, rank


def streak_top(user):
    users = users_with_login_streak()
    leaders = (users.filter(is_active=True, login_streak__gt=0)
               .only('pk', 'username', 'first_name', 'is_staff', 'is_superuser')
               .order_by('-login_streak', 'username', 'pk')[:10])
    rows = []
    current = None
    for position, leader in enumerate(leaders, 1):
        rows.append({'rank': position, 'name': leader.first_name.strip() or leader.username,
                     'role': display_role(leader),
                     'streak': leader.login_streak, 'is_own': leader.pk == user.pk})
        if leader.pk == user.pk:
            current = {'rank': position, 'streak': leader.login_streak}
    if current is None:
        streak, rank = _streak_position(users, user)
        current = {'rank': rank, 'streak': streak}
    return {'leaders': rows, 'current': current}
