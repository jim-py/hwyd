from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import DateField, Exists, ExpressionWrapper, F, Func, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from general_app.user_roles import display_role

from .models import UserActivityLog


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


def users_with_login_streak():
    """Length of the consecutive visit chain ending at each user's latest log.

    The newest date without a predecessor starts the latest chain. Both
    date lookups use the existing (user, date) index. A chain has no missing
    dates, so its length is end - start + 1. Avoid joining every visit and
    repeating the chain-start subquery per historical visit inside COUNT.
    No visit history or per-user queries are loaded into Python.
    """
    predecessor = UserActivityLog.objects.filter(
        user_id=OuterRef('user_id'),
        date=ExpressionWrapper(OuterRef('date') - timedelta(days=1), output_field=DateField()),
    )
    starts = (UserActivityLog.objects.filter(user_id=OuterRef('pk'))
              .annotate(has_predecessor=Exists(predecessor))
              .filter(has_predecessor=False).order_by('-date').values('date')[:1])
    ends = UserActivityLog.objects.filter(user_id=OuterRef('pk')).order_by('-date').values('date')[:1]
    return get_user_model().objects.alias(
        streak_start=Subquery(starts),
        streak_end=Subquery(ends),
    ).annotate(login_streak=Coalesce(InclusiveDays(F('streak_end'), F('streak_start')), 0))


def streak_position(user, *, include_rank=True):
    state = users_with_login_streak().filter(pk=user.pk).values('login_streak', 'username').get()
    streak = state['login_streak']
    if not include_rank:
        return streak, None
    eligible = users_with_login_streak().filter(is_active=True, login_streak__gt=0)
    # Use the same ordering as the leaderboard, including its tie breakers.
    preceding = (Q(login_streak__gt=streak)
                 | Q(login_streak=streak, username__lt=state['username'])
                 | Q(login_streak=streak, username=state['username'], pk__lt=user.pk))
    rank = 1 + eligible.filter(preceding).count() if user.is_active and streak else None
    return streak, rank


def streak_top(user):
    leaders = (users_with_login_streak().filter(is_active=True, login_streak__gt=0)
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
        streak, rank = streak_position(user)
        current = {'rank': rank, 'streak': streak}
    return {'leaders': rows, 'current': current}
