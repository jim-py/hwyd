"""A read-only monthly snapshot. No comments, identities or presentation fields."""
import hashlib
import json
from calendar import monthrange
from datetime import date

from .models import Activities
from .year_stats import enabled_habit_days


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def monthly_snapshot(user, month, today):
    year, month_number = map(int, month.split('-'))
    start = date(year, month_number, 1)
    end = date(year, month_number, monthrange(year, month_number)[1])
    through = min(end, today)
    limit = through.day if through >= start else 0
    rows = list(Activities.objects.filter(user=user, date=month, isGroup=False)
                .order_by('pk').values_list('pk', 'name', 'beginDay', 'endDay', 'onOffCells', 'marks'))
    habits = []
    for _, name, begin, finish, enabled, marks in rows:
        days = list(enabled_habit_days(begin, finish, enabled, marks, limit))
        habits.append({'name': name, 'completed': sum(done for _, done in days), 'available': len(days)})
    completed = sum(habit['completed'] for habit in habits)
    available = sum(habit['available'] for habit in habits)
    facts = {
        'month': month, 'start': start.isoformat(), 'end': end.isoformat(),
        'through': through.isoformat() if limit else None, 'local_date': today.isoformat(),
        'habit_count': len(habits), 'completed': completed, 'available': available,
        'percent': round(completed / available * 100, 1) if available else None,
    }
    revision = hashlib.sha256(compact_json([facts, rows]).encode('utf-8')).hexdigest()
    return {**facts, 'snapshot': revision}, habits
