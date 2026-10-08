"""Current saved habit state, deliberately not an action/event history."""
from calendar import monthrange
from datetime import date, timedelta

from .models import Activities


def habit_statistics(start, end):
    days = {start + timedelta(days=i): {'marks': 0, 'users': set()}
            for i in range((end - start).days + 1)}
    rows = (Activities.objects.filter(isGroup=False, date__gte=start.strftime('%Y-%m'),
                                     date__lte=end.strftime('%Y-%m')).order_by()
            .values_list('pk', 'user_id', 'date', 'beginDay', 'endDay', 'onOffCells', 'marks'))
    malformed = 0
    for pk, user_id, month, begin, finish, enabled_text, marks_text in rows.iterator(chunk_size=500):
        try:
            year, number = map(int, month.split('-'))
            if month != f'{year:04}-{number:02}':
                raise ValueError
            length = monthrange(year, number)[1]
            enabled, marks = enabled_text.split(), marks_text.split()
            # Old rows may contain 31 tokens even for February. Only actual
            # calendar cells inside the selected range can affect this report.
            first = max(0, begin, start.day - 1 if month == start.strftime('%Y-%m') else 0)
            last = min(length - 1, finish, end.day - 1 if month == end.strftime('%Y-%m') else length - 1)
            if begin < 0 or finish >= 31 or begin > finish:
                raise ValueError
            indexes = range(first, last + 1)
            if any(i >= len(enabled) or i >= len(marks) or
                   enabled[i] not in ('True', 'False') or marks[i] not in ('True', 'False')
                   for i in indexes):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            malformed += 1
            continue
        for index in indexes:
            if enabled[index] == 'True' and marks[index] == 'True':
                key = date(year, number, index + 1)
                days[key]['marks'] += 1
                days[key]['users'].add(user_id)
    users = set().union(*(value['users'] for value in days.values()))
    result = [{'date': key, 'marks': value['marks'], 'users': len(value['users'])}
              for key, value in days.items()]
    maximum = max((row['marks'] for row in result), default=0)
    for row in result:
        row['bar'] = round(100 * row['marks'] / maximum) if maximum else 0
    return {'days': result, 'marks': sum(row['marks'] for row in result),
            'users': len(users), 'malformed': malformed, 'start': start, 'end': end}
