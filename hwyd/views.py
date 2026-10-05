# Импорты из стандартной библиотеки
import json
from copy import deepcopy
from calendar import monthrange, day_name, weekday, Calendar
from datetime import datetime, date, timedelta
from locale import setlocale, LC_ALL
from itertools import groupby
from operator import attrgetter

# Импорты из сторонних библиотек
from django.http import HttpResponse, Http404, JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from my_site.embedding import local_dashboard_frame_ancestors
from django.db import transaction
from django.db.models import Value, BooleanField
from django_user_agents.utils import get_user_agent

# Импорты из локальных модулей приложения
from .forms import LoginForm, RegisterForm, SettingsForm, FeedbackForm, theme_colors_form
from .models import Activities, ActivitiesConnection, Settings, CustomFieldsUser, UserActivityLog
from .preferences import FONT_FAMILIES, UI_VISIBILITY_FIELDS, THEME_COLOR_FIELDS
from .streaks import streak_position, streak_top
from .timezones import browser_timezone
from .year_stats import MAX_YEAR, MIN_YEAR, year_completion
from .theme_schedule import (schedule_state, remember_manual_theme, display_theme,
                             ensure_default_themes, lock_theme_owner, scheduled_colors_enabled)
from .view_as import get_viewed_user, is_view_as, preview_requested, preview_read_only, view_as_context
from general_app.models import Guide, UserGuideProgress

setlocale(category=LC_ALL, locale="Russian")


@never_cache
@require_POST
@preview_read_only
def submit_feedback(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Войдите в аккаунт, чтобы отправить сообщение.'}, status=401)
    form = FeedbackForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'Проверьте тип обращения и текст сообщения.',
                             'errors': form.errors}, status=400)
    feedback = form.save(commit=False)
    feedback.user = request.user
    feedback.save()
    return JsonResponse({'ok': True, 'id': feedback.pk}, status=201)


@never_cache
@login_required(login_url='entry')
@require_GET
def top_streak(request):
    return JsonResponse(streak_top(get_viewed_user(request)))


@never_cache
@login_required(login_url='entry')
@require_GET
def year_summary(request, year):
    if not MIN_YEAR <= year <= MAX_YEAR:
        return JsonResponse({'error': 'Год вне доступного диапазона.'}, status=400)
    return JsonResponse(year_completion(get_viewed_user(request), year))


def get_pending_guides(user, read_only=False):
    """
    Возвращает список slug гайдов,
    которые нужно показать пользователю.
    """

    if not user.is_authenticated:
        return []

    guides = Guide.objects.filter(is_active=True)

    pending = []

    for guide in guides:
        if read_only:
            progress = UserGuideProgress.objects.filter(user=user, guide=guide).first()
        else:
            progress, _ = UserGuideProgress.objects.get_or_create(user=user, guide=guide)

        # новый гайд или новая версия
        if progress is None or not progress.viewed or progress.version_seen < guide.version:
            pending.append(guide.slug)
            return pending
    
    return []


@require_POST
def set_timezone(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Некорректный JSON."}, status=400)

    tz = data.get("timezone") if isinstance(data, dict) else None
    if browser_timezone(tz) is None:
        return JsonResponse({"error": "Неизвестный часовой пояс."}, status=400)
    if request.session.get("user_timezone") != tz:
        request.session["user_timezone"] = tz

    return JsonResponse({"status": "ok"})


@login_required(login_url='entry')
def activity_users(request):
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404("Страница не найдена")

    logs = (
        UserActivityLog.objects
        .select_related('user')
        .exclude(user__username='unbroken0886')
        .exclude(user__username='work')
        .order_by('-date', '-last_visit')
    )

    grouped_data = []
    for date, group in groupby(logs, key=attrgetter('date')):
        grouped_data.append({
            'date': date,
            'users': list(group)
        })

    return render(
        request,
        'hwyd/activityUsers.html',
        {
            'grouped_data': grouped_data
        }
    )


@xframe_options_exempt
@local_dashboard_frame_ancestors
@never_cache
@login_required(login_url='entry')
def by_date(request, picked_date):
    """
    Основная функция для отображения таблицы привычек и для обработки POST-запросов, которые
    происходят с обновлением страницы

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: отправка контекста в html шаблон
    """

    if request.method != 'GET' and preview_requested(request):
        return JsonResponse({'error': 'Просмотр пользователя доступен только для чтения.'}, status=403)
    viewed_user = get_viewed_user(request)
    preview = is_view_as(request)

    # Просмотр данных поста
    if request.META['HTTP_HOST'] == '127.0.0.1:8000':
        print(request.POST)
    
    redirect_url = 'by_date'

    # Сохранение настроек
    if request.POST.get('data'):
        settings = Settings.objects.get(user=request.user, selected=True)
        data_values = request.POST['data'].split(',')
        lst = [val == 'true' for val in data_values]

        settings.showCalendar = lst[0]
        settings.showCreateActivity = lst[1]
        settings.showDeleteActivity = lst[2]
        settings.showDeleteAllActivities = lst[3]
        settings.showCreateActivityGroup = lst[4]
        settings.onSounds = lst[5]
        settings.showRowColumnLight = lst[6]
        settings.showActivityDayLight = lst[7]
        settings.showOpenAllGroups = lst[8]
        settings.showTabs = lst[9]
        # A version marker distinguishes unchecked toggles from older clients.
        visibility_version = request.POST.get('uiVisibilityVersion')
        if visibility_version in ('1', '2', '3', '4'):
            for field in UI_VISIBILITY_FIELDS:
                if field == 'showTop' and visibility_version == '1':
                    continue
                if field == 'showViewSwitch' and visibility_version not in ('3', '4'):
                    continue
                if field == 'showThemeSchedule' and visibility_version != '4':
                    continue
                setattr(settings, field, request.POST.get(field) == 'on')
        # settings.name = request.POST['nameSetting']

        if request.POST['radioSettings'] == 'sort':
            settings.enableSortTable = True
            settings.enableOpenCloseGroups = False
        else:
            settings.enableSortTable = False
            settings.enableOpenCloseGroups = True

        if request.POST.get('selectFont') in FONT_FAMILIES:
            settings.fontFamily = request.POST['selectFont']
        settings.vanishing = request.POST['selectFade']
        settings.save()
        return redirect(redirect_url, picked_date)

    # Выбор месяца календарём
    if request.POST.get('chooseDate', False):
        return redirect(redirect_url, request.POST['chooseDate'])

    # Проверка прилетевшей строки на дату
    try:
        date.fromisoformat(picked_date + '-01')
    except ValueError:
        return redirect('index')

    year, month = list(map(int, picked_date.split('-')))  # Разделение строки даты на год и месяц

    # Проверка прилетевшей даты на вхождение в рабочий диапазон
    if (year not in range(2020, 2031)) or (month not in range(1, 13)):
        return redirect('index')
    else:
        activities = Activities.objects.filter(user=viewed_user, date=picked_date)
        hide_activities = [obj.pk for obj in activities if obj.hide]
        groups = [obj for obj in activities if obj.isGroup]
        groups_ids = [obj.pk for obj in groups]
        activated_groups = [obj for obj in activities if obj.isGroup and obj.isOpen]
        settings = Settings.objects.filter(user=viewed_user)
        if not settings.exists() and not preview:
            create_setting(request.user, 'default')
            settings = Settings.objects.filter(user=viewed_user)
        setting = default_setting(viewed_user, 'default') if preview else ''
        for s in settings:
            if s.selected:
                setting = s

        date_now = datetime.now()
        month_name = date(year, month, 1).strftime("%B")  # Имя месяца
        days = monthrange(year, month)[1]  # Количество дней в месяце
        # Отметка нынешнего дня
        today = date_now.day if year == date_now.year and month == date_now.month else -1

        act_connections = ActivitiesConnection.objects.select_related('group').select_related('activity').filter(
            user=viewed_user, activity__user=viewed_user, group__user=viewed_user,
            activity__date=picked_date, group__date=picked_date)

        # Соединяет id активности с id её группы
        connections = {}
        for conn in act_connections:
            connections[conn.activity_id] = conn.group_id

        # Сохраняет комментарии добавленные в клетку
        if request.POST.get('cell', False):
            symbols = request.POST['symbols']
            comment = request.POST['comment']
            if '*' in symbols or '|' in symbols or '*' in comment or '|' in comment:
                return redirect(redirect_url, picked_date)
            activity_day = list(map(int, request.POST['cell'].split('-')))
            activity, day = activities[activity_day[0]], activity_day[1]
            cells_comments = [act.split('*') for act in activity.cellsComments.split('|')]
            cells_comments[day][0] = symbols[:3]
            cells_comments[day][1] = comment[:255]
            activity.cellsComments = '|'.join('*'.join(comm) for comm in cells_comments)
            activity.save()
            return redirect(redirect_url, picked_date)

        # Делает порядок активностей после перетаскивания
        if request.POST.get('activities[]', False):
            # Сбор активностей в один список
            data = []
            for post in dict(request.POST)['activities[]']:
                data.append(post)
            # Замена порядка активностей
            tmp_num = 1
            tmp_num_group = 0
            if data != [activity.name for activity in activities]:
                tmp_activities = []
                query_act = activities.filter(name__in=data)
                for name in data:
                    for activity in query_act:
                        if activity.name == name:
                            tmp_activities.append(activity)
                tmp_act_save = []
                for activity in tmp_activities:
                    if activity.isGroup:
                        tmp_num_group += 1000
                        activity.number = tmp_num_group
                        tmp_num = 1
                    else:
                        if activity.pk in connections:
                            activity.number = tmp_num + tmp_num_group
                            tmp_num += 1
                        else:
                            activity.number = tmp_num_group + tmp_num + 500
                            tmp_num += 1
                    tmp_act_save.append(activity)
                Activities.objects.bulk_update(tmp_act_save, ['number'])
            return redirect(redirect_url, picked_date)

        # Сохранение настроек активностей и групп
        if request.POST.get('activityPk', False):
            pk = int(request.POST['activityPk'])
            activity = ''
            for tmp in activities:
                if tmp.pk == pk:
                    activity = tmp
            old_act = deepcopy(activity)

            if activity.user_id != request.user.pk:
                request.user.is_active = False
                request.user.save()
                return redirect(redirect_url, picked_date)

            begin = int(request.POST['beginDay'])
            end = int(request.POST['endDay'])
            activity.name = request.POST['activityName']
            activity.beginDay = begin - 1 if -1 < begin - 1 < days else 0
            activity.endDay = end - 1 if -1 < end - 1 < days else days - 1
            activity.backgroundColor = request.POST['backgroundColor']
            activity.color = request.POST['color']
            activity.onOffCells = request.POST['onOffCells']
            activity.hide = True if request.POST.get('hideOn', False) == 'on' else False

            if activity.isGroup:
                group_id = activity.pk
                connection_data = []
                for post in request.POST:
                    if post.isnumeric():
                        connection_data.append(int(post))

                conns = [conn.activity_id for conn in act_connections if conn.group_id == group_id]
                if not connection_data == conns:
                    conns_delete = [item for item in conns if item not in connection_data]
                    conns_add = [item for item in connection_data if item not in conns]

                    if conns_delete:
                        for_delete = act_connections.filter(activity_id__in=conns_delete)
                        tmp_number = activity.number
                        tmp_activities = []
                        for connection in for_delete:
                            connection.activity.number = tmp_number + 501
                            tmp_activities.append(connection.activity)
                            tmp_number += 1
                        Activities.objects.bulk_update(tmp_activities, fields=['number'])
                        for_delete.delete()

                    if conns_add:
                        act_connections.filter(activity_id__in=conns_add).delete()
                        tmp_connections = []
                        for activity_id in conns_add:
                            connection = ActivitiesConnection(user=request.user, group_id=group_id,
                                                              activity_id=activity_id)
                            tmp_connections.append(connection)
                        ActivitiesConnection.objects.bulk_create(tmp_connections)

                        tmp_conns = []
                        tmp_number = activity.number
                        for conn in act_connections.filter(group_id=group_id):
                            conn.activity.number = tmp_number + 1
                            tmp_conns.append(conn.activity)
                            tmp_number += 1
                        Activities.objects.bulk_update(tmp_conns, fields=['number'])

                if request.POST['saveWithColor'] == 'true':
                    act_tmp = []
                    for connection in act_connections.filter(group_id=group_id):
                        connection.activity.color = request.POST['color']
                        connection.activity.backgroundColor = request.POST['backgroundColor']
                        act_tmp.append(connection.activity)
                    Activities.objects.bulk_update(act_tmp, fields=['color', 'backgroundColor'])

            activity.save(update_fields=list(activity.get_changed_fields(old_act).keys()))
            return redirect(redirect_url, picked_date)

        # Инициализация словарей прогресса
        groups_progress = {}
        groups_progress_add = {}
        for group in groups:
            groups_progress[group.pk] = []
            groups_progress_add[group.pk] = []

        # Сбор прогресса групп и сколько добавлять процентов к группе за каждую клеточку
        for group in groups:
            activities_connection = []
            for act_conns in act_connections:
                if act_conns.group == group:
                    activities_connection += [act_conns]
            for day in range(days):
                tmp = []
                for connection in activities_connection:
                    if connection.activity.beginDay <= day <= connection.activity.endDay:
                        if connection.activity.onOffCells.split()[day] == 'True':
                            tmp.append(connection.activity.marks.split()[day])
                if len(tmp) == 0:
                    groups_progress[group.pk] += [-1]
                    groups_progress_add[group.pk] += [0.0]
                    continue
                groups_progress[group.pk] += [tmp.count('True') / len(tmp) * 100]
                groups_progress_add[group.pk] += [1 / len(tmp) * 100]

        # Соединяет id группы с теми id активностями, к которым привязана
        group_to_activities = {}
        for conn in act_connections:
            group_to_activities[conn.group_id] = []
        for conn in act_connections:
            group_to_activities[conn.group_id] += [conn.activity_id]

        # Соединяет id активности со статусом её группы открыта/закрыта
        group_open = {}
        for conn in act_connections:
            group_open[conn.activity_id] = conn.group.isOpen

        # Создаем словарь с ключами, которые являются названиями дней недели
        weekdays = {i.lower(): [] for i in day_name}

        # Получаем календарь для текущего месяца
        for day in range(1, monthrange(year, month)[1] + 1):
            # Определяем день недели текущей даты и добавляем ее в соответствующий список в словаре
            weekday_tmp = day_name[weekday(year, month, day)]
            weekdays[weekday_tmp.lower()].append(day)
        tmp_weekdays = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
        for index, weekday_tmp in enumerate(dict(weekdays).keys()):
            weekdays[tmp_weekdays[index]] = weekdays.pop(weekday_tmp)

        # Сбор отметок в словарь и прогресса по активностям в список
        dict_marks = {}
        progress_activities = []
        for index, ac_mark in enumerate(activities):
            dict_marks[index] = [False if elem == 'False' else True for elem in ac_mark.marks.split()]
            if not any(dict_marks[index][::-1]):
                progress_activities.append(f'0/{days if today == -1 else today}')
                continue
            for ind, cell in enumerate(dict_marks[index][::-1]):
                if cell:
                    count_true = dict_marks[index][-ind - 1::-1].count(True)
                    progress_activities.append(f'{count_true}/{days if today == -1 else today}')
                    break

        # Получения активированных клеток для нажатия в шаблоне
        activated_cells = []
        for elem in dict_marks.items():
            for index, day in enumerate(elem[1]):
                if day:
                    activated_cells.append(f'{elem[0]}-{index}')

        # Получения списка выходных
        weekends = []
        for day in (date(year, month, i) for i in range(1, days + 1)):
            weekends.append(True if day.weekday() in [5, 6] else False)

        # Отправка правильного количество дней для мобильной версии
        range_days = [i for i in range(-1, days)]
        if request.user_agent.is_mobile:
            if not range_days[today - 4:today + 2]:
                range_days = range_days[0:6]
            elif len(range_days[today - 4:today + 2]) == 5 and range_days[-1] in range_days[today - 4:today + 2]:
                range_days = range_days[today - 5:today + 1]
            else:
                range_days = range_days[today - 4:today + 2]

        activities = activities.annotate(todayCheck=Value(False, BooleanField()))
        for a in activities:
            a.todayCheck = a.marks.split()[today - 1] if today > 0 else 'False'

        json_activities = list(activities.values())

        # ===== LOGIN STREAK =====
        login_streak, top_rank = streak_position(viewed_user, include_rank=setting.showTop)
        streak_icon = get_streak_icon(login_streak)
        # ========================

        guides = get_pending_guides(viewed_user, read_only=preview)

        context = {'range_activities': activities, 'range_days': range_days, 'weekends': weekends,
                   'cellsToClick': activated_cells, 'date': picked_date, 'onOffDays': [i for i in range(-1, days)][:-1],
                   'settings': setting, 'progress': progress_activities, 'today': today, 'month_name': month_name,
                   'year': year, 'groups_ids': groups_ids, 'days': days, 'groupsToClick': activated_groups,
                   'groups_progress': groups_progress, 'groups_progress_add': groups_progress_add,
                   'lst_group_conns': group_to_activities, 'group_open': group_open, 'connections': connections,
                   'weekdays': weekdays, 'hide_activities': hide_activities, 'all_settings': settings,
                   'calendar': Calendar().monthdatescalendar(year, month), 'month': month,
                   'jsonActivities': json_activities, 'login_streak': login_streak, 'streak_icon': streak_icon,
                   'top_rank': top_rank,
                   'pending_guides': guides, 'guides': len(guides) > 0}

        context['is_habitus_page'] = True
        context.update(view_as_context(request))
        settings_form = SettingsForm(instance=setting, auto_id='%s')
        context['interface_settings'] = [settings_form[name] for name in (
            'showCalendar', 'showCreateActivity', 'showCreateActivityGroup',
            'showDeleteActivity', 'showDeleteAllActivities', 'showOpenAllGroups',
            *UI_VISIBILITY_FIELDS,
        )]
        context['font_families'] = FONT_FAMILIES
        request.habitus_settings = setting
        if not preview:
            ensure_default_themes(request.user)
        context['theme_schedule_state'] = schedule_state(request, apply=not preview, user=viewed_user)
        context['theme_palette'] = context['theme_schedule_state']['colors']
        context['scheduled_theme_colors_enabled'] = scheduled_colors_enabled()
        return render(request, 'hwyd/base.html', context=context)


def get_streak_icon(streak: int) -> str:
    """
    Возвращает FontAwesome иконку уровня streak.
    """

    if streak <= 0:
        return "fa-circle"

    elif streak <= 2:
        return "fa-seedling"

    elif streak <= 6:
        return "fa-fire"

    elif streak <= 13:
        return "fa-fire-flame-curved"

    elif streak <= 29:
        return "fa-star-of-life"

    elif streak <= 59:
        return "fa-trophy"

    elif streak <= 99:
        return "fa-crown"

    elif streak <= 179:
        return "fa-gem"

    elif streak <= 364:
        return "fa-rocket"

    return "fa-star"


@xframe_options_exempt
@local_dashboard_frame_ancestors
@login_required(login_url='entry')
def start(request):
    """
    Функция перехода с пустого маршрута '/' на маршрут нынешнего месяца '/2023-10'

    :param request: request
    :return: перенаправляет в функцию by_date
    """

    current_date = datetime.today()
    url = reverse('by_date', args=[f'{current_date.year}-{current_date.month:0>2}'])
    if is_view_as(request):
        url += f'?view_as={get_viewed_user(request).pk}'
    return redirect(url)


@login_required(login_url='entry')
@preview_read_only
def create_last_activities(request, picked_date):
    """
    Функция для создания активностей прошлого месяца

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: перенаправляет в функцию by_date
    """

    year, month = list(map(int, picked_date.split('-')))
    days = monthrange(year, month)[1]

    # Корректно выбирает прошлый месяц
    if month == 1:
        previous_year, previous_month = year - 1, 12
    else:
        previous_year, previous_month = year, month - 1
    activities = Activities.objects.filter(user=request.user, date=f'{previous_year}-{previous_month:0>2}')
    previous_days = monthrange(previous_year, previous_month)[1]
    previous_first_weekday = weekday(previous_year, previous_month, 1)
    first_weekday = weekday(year, month, 1)

    # Создаёт активности прошлого месяца и заносит их в списки
    all_activities = []
    for activity in activities:
        # Weekday buttons persist as daily flags. Transfer only weekdays whose
        # every occurrence was disabled, using the destination month's calendar.
        previous_cells = activity.onOffCells.split()
        disabled_weekdays = {
            day_of_week for day_of_week in range(7)
            if all(day < len(previous_cells) and previous_cells[day] == 'False'
                   for day in range((day_of_week - previous_first_weekday) % 7, previous_days, 7))
        }
        on_off_cells = ''.join(
            'False ' if (first_weekday + day) % 7 in disabled_weekdays else 'True '
            for day in range(days)
        )
        new_activity = Activities(user=request.user, name=activity.name, date=picked_date, marks='False ' * days,
                       backgroundColor=activity.backgroundColor, number=activity.number, color=activity.color,
                       isGroup=activity.isGroup, isOpen=activity.isOpen, beginDay=0,
                       endDay=days - 1, cellsComments='*|' * days, onOffCells=on_off_cells, hide=activity.hide)
        all_activities.append(new_activity)
    Activities.objects.bulk_create(all_activities)

    # Извлекаем сохраненные объекты из базы данных
    saved_activities = Activities.objects.filter(user=request.user, date=picked_date)

    # Разделяем активности на группы и обычные активности
    new_groups = [activity for activity in saved_activities if activity.isGroup]
    new_activities = [activity for activity in saved_activities if not activity.isGroup]

    # Создаёт словарь пар связей активностей прошлого месяца
    old_dict_pare = {}
    conn = ActivitiesConnection.objects.filter(user=request.user)
    for group in activities.filter(isGroup=True):
        for activity in conn.filter(group=group).select_related('activity'):
            old_dict_pare[activity.activity] = group

    # Создаёт связи новых активностей смотря на пары прошлого месяца
    all_activities_connections = []
    for new_activity in new_activities:
        for old_activity in old_dict_pare.keys():
            if new_activity.name == old_activity.name:
                for new_group in new_groups:
                    if new_group.name == old_dict_pare[old_activity].name:
                        a = ActivitiesConnection(user=request.user, activity=new_activity, group=new_group)
                        all_activities_connections.append(a)
    ActivitiesConnection.objects.bulk_create(all_activities_connections)

    return redirect('by_date', picked_date)


@login_required(login_url='entry')
@preview_read_only
def delete_activity(request):
    """
    Функция удаления активности

    :param request: request
    :return: отправляет пустой ответ, чтобы не было ошибки
    """

    get_object_or_404(Activities, pk=int(request.POST['pk']), user=request.user).delete()
    return HttpResponse()


@login_required(login_url='entry')
@require_POST
@preview_read_only
def global_colors(request, picked_date):
    """
    Функция для сохранения настроек цветов

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: перенаправляет в функцию by_date
    """

    with transaction.atomic():
        lock_theme_owner(request.user.pk)
        ensure_default_themes(request.user)
        theme = display_theme(request)
        if not scheduled_colors_enabled() and theme.pk is None:
            create_setting(request.user, 'default')
            theme = display_theme(request)
        form = theme_colors_form(request.POST, instance=theme)
        if not form.is_valid():
            return JsonResponse({'error': 'Цвет должен иметь формат #RRGGBB.'}, status=400)
        form.save()
        remember_manual_theme(request, theme)

    return redirect('by_date', picked_date)


@login_required(login_url='entry')
@preview_read_only
def create_activity(request, picked_date, is_group):
    """
    Функция для создания активности

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :param is_group: булево для проверки создания активности или же группы
    :return: перенаправляет в функцию by_date
    """

    inp = 'createActivityGroupInput' if is_group else 'createActivityInput'
    try:
        Activities.objects.get(user=request.user, name=request.POST[inp], date=picked_date)
    except Activities.DoesNotExist:
        activities = Activities.objects.filter(user=request.user, date=picked_date)
        if activities:
            number = activities[len(activities) - 1].number + 1
        else:
            number = 0
        number = number + 1000 if is_group else number
        year, month = list(map(int, picked_date.split('-')))  # Разделение строки даты на массив года и месяца
        days = monthrange(year, month)[1]  # Количество дней в месяце
        Activities.objects.create(name=request.POST[inp], date=picked_date, color='#000000', backgroundColor='#ffffff',
                                  marks='False ' * days, onOffCells='True ' * days, number=number, isGroup=is_group,
                                  beginDay=0, endDay=days - 1, isOpen=False, cellsComments='*|' * days,
                                  user=request.user, hide=False)

    return redirect('by_date', picked_date)


@never_cache
@login_required(login_url='entry')
def get_comments(request, picked_date):
    """
    Функция получения комментариев активности

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: отправляет комментарии активности
    """

    activity, day = get_activity_day(request.POST['cell'], get_viewed_user(request), picked_date)
    return HttpResponse(activity.cellsComments)


@login_required(login_url='entry')
@preview_read_only
def check_cell(request, picked_date):
    """
    Функция для отметки в базе данных нажатой клетки

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: отправляет пустой ответ, чтобы не было ошибки
    """

    activity, day = get_activity_day(request.POST['checkboxToCheck'], request.user, picked_date)
    marks_db = activity.marks.split()
    marks_db[day] = 'False' if marks_db[day] == 'True' else 'True'
    activity.marks = ' '.join(marks_db)
    activity.save(update_fields=['marks'])
    return HttpResponse()


@login_required(login_url='entry')
@require_POST
@preview_read_only
def open_group(request):
    """
    Функция для сохранения открытия группы в базе данных

    :param request: request
    :return: возвращает сохранённое состояние группы
    """

    try:
        group_id = int(request.POST.get('openedGroup', ''))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Некорректная группа.'}, status=400)
    group = get_object_or_404(Activities, pk=group_id, user=request.user, isGroup=True)
    collapsed = request.POST.get('collapsed')
    if collapsed not in (None, 'true', 'false'):
        return JsonResponse({'error': 'Некорректное состояние группы.'}, status=400)
    # The legacy isOpen field means collapsed in the existing templates.
    group.isOpen = not group.isOpen if collapsed is None else collapsed == 'true'
    group.save(update_fields=['isOpen'])
    return JsonResponse({'group_id': group.pk, 'collapsed': group.isOpen})


@login_required(login_url='entry')
@require_POST
@preview_read_only
def open_all(request, picked_date):
    """
    Функция для сохранения открытия всех групп в базе даннах

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: возвращает сохранённые состояния групп
    """

    groups = Activities.objects.filter(user=request.user, date=picked_date, isGroup=True)
    opened_groups = []
    for group in groups:
        opened_groups.append(group.isOpen)
    collapsed = request.POST.get('collapsed')
    if collapsed not in (None, 'true', 'false'):
        return JsonResponse({'error': 'Некорректное состояние группы.'}, status=400)
    res = not any(opened_groups) if collapsed is None else collapsed == 'true'
    for group in groups:
        group.isOpen = res
    Activities.objects.bulk_update(groups, ['isOpen'])
    return JsonResponse({'groups': [{'id': group.pk, 'collapsed': group.isOpen} for group in groups]})


def get_activity_day(cell, user, picked_date):
    """
    Функция для обработки данных id из POST-запроса

    :param cell: id клетки из POST в формате 'activity-day', пример: '1-5' вторая активность, шестой день
    :param user: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: отправляет объект активности и день
    """

    activities = Activities.objects.filter(user=user, date=picked_date)
    activity_day = list(map(int, cell.split('-')))
    return activities[activity_day[0]], activity_day[1]


@login_required(login_url='entry')
@require_POST
@preview_read_only
def delete_all(request, picked_date):
    """
    Функция удаления всех активностей

    :param request: request
    :param picked_date: полученная дата из маршрута формата 'YYYY-MM' '2023-10'
    :return: отправляет пустой ответ, чтобы не было ошибки
    """

    Activities.objects.filter(user=request.user, date=picked_date).delete()
    return HttpResponse()


@preview_read_only
def change_setting(request):
    settings = Settings.objects.filter(user=request.user)
    pk_sett = int(request.POST['setting'])
    update_settings = []
    for setting in settings:
        if setting.selected:
            setting.selected = False
            update_settings.append(setting)
        if setting.pk == pk_sett:
            setting.selected = True
            update_settings.append(setting)
    Settings.objects.bulk_update(update_settings, fields=['selected'])

    return HttpResponse()


@preview_read_only
def add_setting(request):
    if request.method == 'POST':
        # Снимаем выделение с текущей выбранной настройки
        Settings.objects.filter(user=request.user, selected=True).update(selected=False)
        
        # Создаем новую настройку
        name = request.POST.get('nameSetting', 'Новая настройка')
        create_setting(request.user, name)
    return HttpResponseRedirect(reverse('edit_settings'))


def create_setting(user, name):
    default_setting(user, name).save()


def default_setting(user, name):
    """Display the normal first-visit preset without writing a preview owner's data."""
    return Settings(
        user=user,
        backgroundColor='#f0f0f0',
        tableHeadColorWeekend='#eeb3b3',
        tableHeadColor='#e6e4ce',
        tableHeadTextColor='#000000',
        showCalendar=True,
        showCreateActivity=True,
        showDeleteAllActivities=True,
        showDeleteActivity=False,
        showCreateActivityGroup=True,
        enableSortTable=False,
        enableOpenCloseGroups=True,
        onSounds=True,
        showRowColumnLight=True,
        showActivityDayLight=True,
        rowColumnLight='#e7e7e7',
        fontFamily='Inter',
        showOpenAllGroups=True,
        showTabs=True,
        selected=True,
        name=name
    )


@preview_read_only
def delete_setting(request, setting_id):
    if request.method == 'POST':
        setting = Settings.objects.filter(id=setting_id, user=request.user).first()
        if setting:
            setting.delete()
            # После удаления выбрать любую другую настройку, если остались
            next_setting = Settings.objects.filter(user=request.user).first()
            if next_setting:
                next_setting.selected = True
                next_setting.save()
    return HttpResponseRedirect(reverse('edit_settings'))


@login_required(login_url='entry')
def user_logout(request):
    """
    Функция для выхода пользователя

    :param request: request
    :return: перенаправляет на начальный маршрут '/'
    """

    logout(request)
    return redirect('entry')


@never_cache
@login_required(login_url='entry')
def export_data_as_json(request):
    user = get_viewed_user(request)

    # Фильтруем привычки (isGroup=False) и сортируем по дате, затем по имени
    habits = Activities.objects.filter(user=user, isGroup=False).values(
        'id', 'name', 'color', 'date', 'marks'
    ).order_by('date', 'name')

    # Фильтруем группы (isGroup=True) и сортируем по дате, затем по имени
    groups_query = Activities.objects.filter(user=user, isGroup=True).values(
        'id', 'name', 'color', 'date'
    ).order_by('date', 'name')

    # Фильтруем связи между группами и привычками
    connections = ActivitiesConnection.objects.filter(
        user=user, group__user=user, activity__user=user).values('group_id', 'activity_id')

    result = []  # Список для привычек
    groups = []  # Список для групп

    # Обработка привычек
    for activity in habits:
        name = activity["name"]
        color = activity["color"]
        date = activity["date"]  # Формат даты: YYYY-MM
        marks = activity["marks"].split(sep=" ")  # Разделяем отметки "False True False"

        # Преобразуем дату в объект datetime для обработки дней
        year, month = map(int, date.split('-'))
        days_in_month = monthrange(year, month)[1]  # Определяем количество дней в месяце
        base_date = datetime(year, month, 1)  # Начало месяца

        # Найти группу, к которой принадлежит активность
        group_name = None  # Название группы
        related_groups = [conn['group_id'] for conn in connections if conn['activity_id'] == activity['id']]
        if related_groups:
            # Получить название первой группы (если активность принадлежит нескольким группам, можно изменить логику)
            group_name = Activities.objects.filter(id=related_groups[0], user=user).values_list('name', flat=True).first()

        # Ограничиваем обработку только количеством дней в месяце
        for index, mark in enumerate(marks[:days_in_month]):  # Отсекаем лишние дни
            day_date = base_date + timedelta(days=index)  # Вычисляем дату для каждой отметки
            result.append({
                "name": name,
                "color": color,
                "date": day_date.strftime("%Y-%m-%d"),  # Преобразуем дату в строку
                "mark": mark,  # True или False
                "group": group_name  # Название группы
            })

    # Обработка групп
    for group in groups_query:
        group_id = group['id']
        group_name = group['name']
        group_color = group['color']
        group_date = group['date']

        # Найти все связанные привычки для группы
        related_activities = [activity for activity in habits if activity['id'] in [
            conn['activity_id'] for conn in connections if conn['group_id'] == group_id
        ]]

        # Расчет процента выполнения группы по дням
        days_in_month = monthrange(*map(int, group_date.split('-')))[1]  # Количество дней в месяце
        total_days = days_in_month
        day_completion = [0] * total_days  # Массив для учета выполнения по дням

        for activity in related_activities:
            marks = activity['marks'].split(sep=" ")[:total_days]  # Ограничиваем количеством дней месяца
            for day_index, mark in enumerate(marks):
                if mark == "True":
                    day_completion[day_index] += 1

        # Рассчитываем общий процент выполнения группы по дням
        overall_percentage = round(sum(day_completion) / (total_days * len(related_activities)) * 100) if related_activities else 0

        # Добавляем данные о группе
        groups.append({
            "name": group_name,
            "color": group_color,
            "date": group_date,
            "completion_percentage": overall_percentage,
            "daily_completion": [
                {
                    "day": day_index + 1,
                    "completed": day_completion[day_index],
                    "total": len(related_activities),
                    "percentage": round(day_completion[day_index] / len(related_activities) * 100) if len(related_activities) > 0 else 0
                }
                for day_index in range(total_days)
            ]
        })

    # Возвращаем данные в формате JSON
    return JsonResponse({"activities": result, "groups": groups})


@login_required(login_url='entry')
@preview_read_only
def edit_settings(request):
    settings_list = Settings.objects.filter(user=request.user).order_by('name')
    current_setting = settings_list.filter(selected=True).first()
    ensure_default_themes(request.user)
    theme = display_theme(request)
    color_form = theme_colors_form(instance=theme)

    if request.method == 'POST' and current_setting:
        data = request.POST.copy()
        if request.POST.get('uiVisibilityVersion') not in ('3', '4'):
            # Older settings pages did not contain the new checkbox.
            if current_setting.showViewSwitch:
                data['showViewSwitch'] = 'on'
            else:
                data.pop('showViewSwitch', None)
        if request.POST.get('uiVisibilityVersion') != '4':
            if current_setting.showThemeSchedule:
                data['showThemeSchedule'] = 'on'
            else:
                data.pop('showThemeSchedule', None)
        form = SettingsForm(data, instance=current_setting)
        has_colors = any(field in data for field in THEME_COLOR_FIELDS)
        with transaction.atomic():
            lock_theme_owner(request.user.pk)
            if has_colors:
                ensure_default_themes(request.user)
                theme = display_theme(request)
                color_form = theme_colors_form(data, instance=theme)
            if form.is_valid() and (not has_colors or color_form.is_valid()):
                form.save()
                if has_colors:
                    color_form.save()
                    remember_manual_theme(request, theme)
                return redirect('edit_settings')
    else:
        form = SettingsForm(instance=current_setting) if current_setting else None

    context = {
        'settings_list': settings_list,
        'current_setting': current_setting,
        'form': form,
        'settings_fields': [*color_form, *form] if form else [],
    }
    return render(request, 'hwyd/settings.html', context)


@login_required(login_url='entry')
@preview_read_only
def select_setting(request, pk):
    """Смена активной настройки (только среди своих)"""
    
    # Получаем настройку только текущего пользователя или 404
    setting = get_object_or_404(Settings, pk=pk, user=request.user)

    # Если уже выбрана — просто редирект
    if setting.selected:
        return redirect('edit_settings')

    # Снимаем выделение со всех настроек пользователя
    Settings.objects.filter(user=request.user, selected=True).update(selected=False)

    # Отмечаем выбранную
    setting.selected = True
    setting.save(update_fields=["selected"])

    return redirect('edit_settings')
