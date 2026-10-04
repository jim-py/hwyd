"""Copy Settings color presets into ScheduledTheme without schema changes.

python scripts/import_settings_themes.py           # read-only preview
python scripts/import_settings_themes.py --apply   # write the previewed import
"""
import argparse
from dataclasses import dataclass, field
from datetime import time
import os
from pathlib import Path
import re
import sys


class ImportProblem(Exception):
    pass


@dataclass
class OwnerPlan:
    user_id: int
    create: list = field(default_factory=list)
    skipped: int = 0
    errors: list = field(default_factory=list)


def parse_time(value):
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise argparse.ArgumentTypeError('Время должно быть в формате ЧЧ:ММ.')
    hour, minute = map(int, value.split(':'))
    return time(hour, minute)


def check_database(using):
    from django.contrib.auth import get_user_model
    from django.db import connections
    from hwyd.models import Settings, ScheduledTheme

    if using not in connections:
        raise ImportProblem(f'Неизвестный alias БД: {using}.')
    connection = connections[using]
    if connection.vendor not in ('sqlite', 'mysql'):
        raise ImportProblem('Скрипт рассчитан на SQLite и MySQL.')
    models = (Settings, ScheduledTheme, get_user_model())
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        for model in models:
            table = model._meta.db_table
            if table not in tables:
                raise ImportProblem(f'Отсутствует таблица {table}. Скрипт переносит данные, но не создаёт схему.')
            columns = {column.name for column in connection.introspection.get_table_description(cursor, table)}
            missing = {field.column for field in model._meta.local_fields} - columns
            if missing:
                raise ImportProblem(f'В {table} отсутствуют поля: {", ".join(sorted(missing))}.')
        if connection.vendor == 'mysql':
            # MySQL 5.7 CHECK is not enforced; use Python validation below.
            # Per-owner rollback and SELECT FOR UPDATE require InnoDB.
            names = [model._meta.db_table for model in models]
            cursor.execute(
                'SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES '
                'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (%s, %s, %s)', names,
            )
            engines = dict(cursor.fetchall())
            if any((engines.get(name) or '').lower() != 'innodb' for name in names):
                raise ImportProblem('Таблицы Settings, ScheduledTheme и пользователей должны использовать InnoDB.')
    return connection.vendor


def build_plan(user_id, start_time, using='default'):
    from django.core.exceptions import ValidationError
    from hwyd.models import Settings, ScheduledTheme
    from hwyd.preferences import THEME_COLOR_FIELDS

    plan = OwnerPlan(user_id)
    presets = list(Settings.objects.using(using).filter(user_id=user_id).order_by('pk').values(
        'pk', 'name', 'selected', *THEME_COLOR_FIELDS,
    ))
    if len(presets) > 1440:
        plan.errors.append(f'user={user_id}: более 1440 Settings, не хватает уникальных минут суток.')
        return plan
    existing = list(ScheduledTheme.objects.using(using).filter(user_id=user_id).values(
        'name', 'activation_time', 'is_enabled', *THEME_COLOR_FIELDS,
    ))

    def signature(row):
        return (row['name'], row['activation_time'], *(str(row[field]).lower() for field in THEME_COLOR_FIELDS))

    fingerprints = {}
    for row in existing:
        fingerprints.setdefault(signature(row), set()).add(row['is_enabled'])
    active_times = {row['activation_time'] for row in existing if row['is_enabled']}
    first_minute = start_time.hour * 60 + start_time.minute
    for offset, preset in enumerate(presets):
        minute = (first_minute + offset) % 1440
        activation = time(minute // 60, minute % 60)
        enabled = bool(preset['selected'])
        name = (preset['name'].strip() or 'Тема')[:80]
        colors = {field: preset[field] for field in THEME_COLOR_FIELDS}
        theme = ScheduledTheme(user_id=user_id, name=name, activation_time=activation,
                               is_enabled=enabled, active_time=activation if enabled else None, **colors)
        try:
            theme.clean_fields(exclude=('id', 'user', 'active_time', 'created_at', 'updated_at'))
        except ValidationError as exc:
            fields = ', '.join(sorted(exc.message_dict))
            plan.errors.append(f'Settings #{preset["pk"]}: некорректные поля: {fields}.')
            continue
        key = signature({'name': name, 'activation_time': activation, **colors})
        if key in fingerprints:
            if enabled in fingerprints[key]:
                plan.skipped += 1
            else:
                plan.errors.append(f'Settings #{preset["pk"]}: совпадающая тема имеет другое состояние активности; '
                                   'существующие темы не перезаписываются.')
            continue
        if enabled and activation in active_times:
            plan.errors.append(f'Settings #{preset["pk"]}: на {activation:%H:%M} уже включена другая тема.')
            continue
        plan.create.append((preset['pk'], theme))
    return plan


def import_themes(*, apply=False, start_time=time(8), user_ids=None, using='default', output=print):
    from django.db import transaction
    from hwyd.models import Settings, ScheduledTheme
    from hwyd.theme_schedule import lock_theme_owner

    vendor = check_database(using)
    queryset = Settings.objects.using(using)
    if user_ids:
        queryset = queryset.filter(user_id__in=user_ids)
    owners = list(queryset.order_by('user_id').values_list('user_id', flat=True).distinct())
    # Complete the read-only preflight before any writes, including invalid colors
    # and conflicts with previously configured schedules.
    plans = [build_plan(owner, start_time, using) for owner in owners]
    output(f'БД: {using} ({vendor}). Режим: {"ЗАПИСЬ" if apply else "ПРЕДПРОСМОТР"}.')
    for plan in plans:
        output(f'user={plan.user_id}: создать {len(plan.create)}, уже есть {plan.skipped}.')
        for preset_id, theme in plan.create:
            output(f'  Settings #{preset_id} -> {theme.name!r}, {theme.activation_time:%H:%M}, '
                   f'{"включена" if theme.is_enabled else "выключена"}')
    problems = [error for plan in plans for error in plan.errors]
    if problems:
        raise ImportProblem('Проверка не пройдена; данные не записаны.\n' + '\n'.join(problems))
    created = 0
    skipped = sum(plan.skipped for plan in plans)
    if apply:
        skipped = 0
        for owner in owners:
            # Short transactions, one owner at a time. Fresh reads after locking
            # also protect against another simultaneous run of this importer.
            with transaction.atomic(using=using):
                lock_theme_owner(owner, using)
                plan = build_plan(owner, start_time, using)
                if plan.errors:
                    raise ImportProblem(f'Данные изменились после предпросмотра. Уже создано {created}. '
                                        'Текущий пользователь не изменён; повторный запуск пропустит готовые темы.\n'
                                        + '\n'.join(plan.errors))
                themes = [theme for _, theme in plan.create]
                # active_time is explicitly populated; no reliance on CHECK,
                # partial indexes, ignore_conflicts, or returned MySQL insert IDs.
                ScheduledTheme.objects.using(using).bulk_create(themes, batch_size=200)
                created += len(themes)
                skipped += plan.skipped
    planned = sum(len(plan.create) for plan in plans)
    output(f'Итого: {"создано " + str(created) if apply else "будет создано " + str(planned)}, '
           f'пропущено существующих {skipped}.')
    return {'planned': planned, 'created': created, 'skipped': skipped}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Копирование цветов всех Settings в ScheduledTheme без миграций.')
    parser.add_argument('--apply', action='store_true', help='Записать темы; без этого флага только предпросмотр.')
    parser.add_argument('--start-time', type=parse_time, default=time(8), help='Начало списка каждого пользователя (08:00).')
    parser.add_argument('--user-id', type=int, action='append', help='Ограничить перенос пользователем; можно повторять.')
    parser.add_argument('--database', default='default', help='Alias БД из Django settings.')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_site.settings')
    import django
    django.setup()
    from django.db import DatabaseError
    try:
        import_themes(apply=args.apply, start_time=args.start_time, user_ids=args.user_id, using=args.database)
    except ImportProblem as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except DatabaseError as exc:
        # Do not print connection details or application credentials.
        print(f'Ошибка БД ({type(exc).__name__}). Проверьте схему, доступ и блокировки. '
              'Возможен частичный перенос предыдущих пользователей; повторите предпросмотр.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
