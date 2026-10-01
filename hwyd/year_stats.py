from calendar import monthrange

from .models import Activities


MIN_YEAR = 2020
MAX_YEAR = 2030


def year_completion(user, year):
    """Aggregate enabled habit-days from one bounded query of monthly rows."""
    months = [
        {'month': month, 'days': [{'completed': 0, 'total': 0}
                                for _ in range(monthrange(year, month)[1])]}
        for month in range(1, 13)
    ]
    # These fields use the existing tracker storage contract. A foreign-key
    # index restricts to one owner; a lexical YYYY-MM range restricts the year.
    # No default sorting, joins, group lookups or deferred-field queries.
    rows = (Activities.objects.filter(user=user, isGroup=False,
                                      date__gte=f'{year:04}-01',
                                      date__lt=f'{year + 1:04}-01')
            .order_by().values_list('date', 'beginDay', 'endDay', 'onOffCells', 'marks'))
    for month_key, begin, end, enabled_text, marks_text in rows.iterator(chunk_size=500):
        try:
            month = int(month_key[5:])
        except ValueError:
            continue
        if not 1 <= month <= 12 or month_key != f'{year:04}-{month:02}':
            continue
        days = months[month - 1]['days']
        enabled = enabled_text.split()
        marks = marks_text.split()
        for index in range(max(0, begin), min(end + 1, len(days), len(enabled))):
            if enabled[index] != 'True':
                continue
            days[index]['total'] += 1
            if index < len(marks) and marks[index] == 'True':
                days[index]['completed'] += 1
    return {'year': year, 'months': months}
