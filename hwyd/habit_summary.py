"""A read-only monthly snapshot. No comments, identities or presentation fields."""
import hashlib
import json
from calendar import monthrange
from datetime import date
from fractions import Fraction

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
        completed = sum(done for _, done in days)
        comparison = None
        # Adjacent weeks in the same monthly row keep habit identity and weekdays.
        # A different availability mask may mean a changed schedule: do not compare.
        if limit >= 14:
            by_day = dict(days)
            previous = [by_day.get(index) for index in range(limit - 14, limit - 7)]
            current = [by_day.get(index) for index in range(limit - 7, limit)]
            if [value is not None for value in previous] == [value is not None for value in current]:
                available = sum(value is not None for value in current)
                if available:
                    previous_done, current_done = sum(value is True for value in previous), sum(value is True for value in current)
                    comparison = {
                        'previous_completed': previous_done, 'previous_available': available,
                        'current_completed': current_done, 'current_available': available,
                        'previous_percent': round(previous_done / available * 100, 1),
                        'current_percent': round(current_done / available * 100, 1),
                        'delta_pp': round((current_done - previous_done) / available * 100, 1),
                    }
        habits.append({'name': name, 'completed': completed, 'available': len(days),
                       'percent': round(completed / len(days) * 100, 1) if days else None,
                       'comparison': comparison})
    completed = sum(habit['completed'] for habit in habits)
    available = sum(habit['available'] for habit in habits)
    changes = {'improvements': [], 'declines': []}
    for habit in habits:
        if habit['comparison'] and habit['comparison']['delta_pp']:
            direction = 'improvements' if habit['comparison']['delta_pp'] > 0 else 'declines'
            changes[direction].append({'name': habit['name'], **habit['comparison']})
    regularity = {'most_regular': [], 'least_regular': []}
    ranked = sorted((habit for habit in habits if habit['available']),
                    key=lambda habit: Fraction(habit['completed'], habit['available']))
    if len(ranked) > 1:
        low, high = (Fraction(habit['completed'], habit['available']) for habit in (ranked[0], ranked[-1]))
        if low != high:
            for label, rate in (('most_regular', high), ('least_regular', low)):
                regularity[label] = [{'name': habit['name'], 'percent': habit['percent']} for habit in ranked
                                    if Fraction(habit['completed'], habit['available']) == rate]
    comparison_period = None
    if limit >= 14:
        comparison_period = {
            'previous_start': start.replace(day=limit - 13).isoformat(),
            'previous_end': start.replace(day=limit - 7).isoformat(),
            'current_start': start.replace(day=limit - 6).isoformat(), 'current_end': through.isoformat(),
            'compared_count': sum(habit['comparison'] is not None for habit in habits),
        }
    facts = {
        'month': month, 'start': start.isoformat(), 'end': end.isoformat(),
        'through': through.isoformat() if limit else None, 'local_date': today.isoformat(),
        'habit_count': len(habits), 'completed': completed, 'available': available,
        'percent': round(completed / available * 100, 1) if available else None,
        'habits': habits, 'changes': changes, 'regularity': regularity, 'comparison_period': comparison_period,
    }
    revision = hashlib.sha256(compact_json([facts, rows]).encode('utf-8')).hexdigest()
    return {**facts, 'snapshot': revision}, habits
