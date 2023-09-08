import calendar
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from .models import Activities, Settings, ActivitiesConnection
from calendar import monthrange
from datetime import datetime, date
import locale
from .forms import RegisterForm, LoginForm
import copy

locale.setlocale(
    category=locale.LC_ALL,
    locale="Russian"
)


@login_required(login_url='start')
def by_date(request, picked_date):
    # Определение версии сайта (мобильная или компьютерная)
    try:
        redirect_url = 'mobile_by_date' if '/m' in request.META.get('HTTP_REFERER') else 'by_date'
    except TypeError:
        redirect_url = 'by_date'

    if request.POST.get('data'):
        settings = Settings.objects.get(user=request.user)
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

        if request.POST['radioSettings'] == 'sort':
            settings.enableSortTable = True
            settings.enableOpenCloseGroups = False
        else:
            settings.enableSortTable = False
            settings.enableOpenCloseGroups = True

        settings.fontFamily = request.POST['selectFont']
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

    picked_date_lst = list(map(int, picked_date.split('-')))  # Разделение строки даты на массив года и месяца

    # Проверка прилетевшей даты на вхождение в рабочий диапазон
    if (picked_date_lst[0] not in range(2020, 2031)) or (picked_date_lst[1] not in range(1, 13)):
        return redirect('index')
    else:
        activities = Activities.objects.filter(user=request.user, date=picked_date)
        groups = [obj for obj in activities if obj.isGroup]
        groups_ids = [obj.pk for obj in groups]
        activated_groups = [obj for obj in activities if obj.isGroup and obj.isOpen]
        settings = Settings.objects.get(user=request.user)

        date_now = datetime.now()
        month_name = date(picked_date_lst[0], picked_date_lst[1], 1).strftime("%B")  # Имя месяца
        days = monthrange(picked_date_lst[0], picked_date_lst[1])[1]  # Количество дней в месяце
        # Отметка нынешнего дня
        today = date_now.day if picked_date_lst[0] == date_now.year and picked_date_lst[1] == date_now.month else -1

        act_connections = ActivitiesConnection.objects.select_related('group').select_related('activity').filter(user=request.user, activity__date=picked_date)

        connections = {}
        for conn in act_connections:
            connections[conn.activity_id] = conn.group_id

        if request.POST:
            print(request.POST)

        if request.POST.get('cell', False):
            if '*' in request.POST['symbols'] or '|' in request.POST['symbols'] or '*' in request.POST['comment'] or '|' in request.POST['comment']:
                return redirect(redirect_url, picked_date)
            activity_day = list(map(int, request.POST['cell'].split('-')))
            activity, day = activities[activity_day[0]], activity_day[1]
            cells_comments = [act.split('*') for act in activity.cellsComments.split('|')]
            cells_comments[day][0] = request.POST['symbols'][:3]
            cells_comments[day][1] = request.POST['comment'][:255]
            activity.cellsComments = '|'.join('*'.join(comm) for comm in cells_comments)
            activity.save()
            return redirect(redirect_url, picked_date)

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
                        try:
                            check = connections[activity.pk]
                            activity.number = tmp_num + tmp_num_group
                            tmp_num += 1
                        except KeyError:
                            activity.number = tmp_num_group + tmp_num + 500
                            tmp_num += 1
                    tmp_act_save.append(activity)
                Activities.objects.bulk_update(tmp_act_save, ['number'])
            return redirect(redirect_url, picked_date)

        if request.POST.get('activityPk', False):
            pk = int(request.POST['activityPk'])
            activity = ''
            for tmp in activities:
                if tmp.pk == pk:
                    activity = tmp
            old_act = copy.deepcopy(activity)

            if activity.user_id != request.user.pk:
                request.user.is_active = False
                request.user.save()
                return redirect(redirect_url, picked_date)

            activity.name = request.POST['activityName']
            activity.beginDay = int(request.POST['beginDay']) - 1 if -1 < int(request.POST['beginDay']) - 1 < days else 0
            activity.endDay = int(request.POST['endDay']) - 1 if -1 < int(request.POST['endDay']) - 1 < days else days - 1
            activity.backgroundColor = request.POST['backgroundColor']
            activity.color = request.POST['color']
            activity.onOffCells = request.POST['onOffCells']

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
                            connection = ActivitiesConnection(user=request.user, group_id=group_id, activity_id=activity_id)
                            tmp_connections.append(connection)
                        ActivitiesConnection.objects.bulk_create(tmp_connections)

                        tmp_conns = []
                        tmp_number = activity.number
                        for conn in act_connections.filter(group_id=group_id):
                            conn.activity.number = tmp_number + 1
                            tmp_conns.append(conn.activity)
                            tmp_number += 1
                        Activities.objects.bulk_update(tmp_conns, fields=['number'])

                if request.POST['saveWithColor']:
                    act_tmp = []
                    for connection in act_connections.filter(group_id=group_id):
                        connection.activity.color = request.POST['color']
                        connection.activity.backgroundColor = request.POST['backgroundColor']
                        act_tmp.append(connection.activity)
                    Activities.objects.bulk_update(act_tmp, fields=['color', 'backgroundColor'])

            activity.save(update_fields=list(activity.get_changed_fields(old_act).keys()))
            return redirect(redirect_url, picked_date)

        groups_progress = {}
        for group in groups:
            groups_progress[group.pk] = []

        groups_progress_add = {}
        for group in groups:
            groups_progress_add[group.pk] = []

        for group in groups:
            activities_connection = []
            for act_conns in act_connections:
                if act_conns.group == group:
                    activities_connection += [act_conns]
            for day in range(days):
                tmp = []
                for connection in activities_connection:
                    if (connection.activity.beginDay <= day <= connection.activity.endDay) and connection.activity.onOffCells.split()[day] == 'True':
                        tmp.append(connection.activity.marks.split()[day])
                if len(tmp) == 0:
                    groups_progress[group.pk] += [-1]
                    groups_progress_add[group.pk] += [0.0]
                    continue
                groups_progress[group.pk] += [tmp.count('True') / len(tmp) * 100]
                groups_progress_add[group.pk] += [1 / len(tmp) * 100]

        lst_group_conns = {}
        for conn in act_connections:
            lst_group_conns[conn.group_id] = []
        for conn in act_connections:
            lst_group_conns[conn.group_id] += [conn.activity_id]

        group_open = {}
        for conn in act_connections:
            group_open[conn.activity_id] = conn.group.isOpen

        # Создаем словарь с ключами, которые являются названиями дней недели
        weekdays = {i.lower(): [] for i in calendar.day_name}

        now = datetime.now()
        month = now.month

        # Получаем календарь для текущего месяца
        for day in range(1, calendar.monthrange(now.year, month)[1] + 1):
            # Определяем день недели текущей даты и добавляем ее в соответствующий список в словаре
            weekday = calendar.day_name[calendar.weekday(now.year, month, day)]
            weekdays[weekday.lower()].append(day)
        tmp_weekdays = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
        for index, weekday in enumerate(dict(weekdays).keys()):
            weekdays[tmp_weekdays[index]] = weekdays.pop(weekday)

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
        for day in (date(picked_date_lst[0], picked_date_lst[1], i) for i in range(1, days + 1)):
            weekends.append(True if day.weekday() in [5, 6] else False)

        range_days = [i for i in range(-1, days)]
        if '/m' in request.path:
            if not range_days[today - 4:today + 2]:
                range_days = range_days[0:6]
            elif len(range_days[today - 4:today + 2]) == 5 and range_days[-1] in range_days[today - 4:today + 2]:
                range_days = range_days[today - 5:today + 1]
            else:
                range_days = range_days[today - 4:today + 2]

        context = {'range_activities': activities, 'range_days': range_days, 'onOffDays': [i for i in range(-1, days)][:-1],
                   'weekends': weekends, 'cellsToClick': activated_cells, 'date': picked_date,
                   'settings': settings, 'progress': progress_activities, 'today': today, 'month_name': month_name,
                   'year': picked_date_lst[0], 'groups_ids': groups_ids, 'days': days, 'groupsToClick': activated_groups,
                   'groups_progress': groups_progress, 'groups_progress_add': groups_progress_add, 'connections': connections,
                   'lst_group_conns': lst_group_conns, 'group_open': group_open, 'weekdays': weekdays}

        return render(request, 'base.html', context=context)


@login_required(login_url='start')
def start(request):
    current_date = datetime.today()
    return redirect('by_date', f'{current_date.year}-{current_date.month:0>2}')


@login_required(login_url='start')
def create_last_activities(request, picked_date):
    picked_date_lst = list(map(int, picked_date.split('-')))
    days = monthrange(picked_date_lst[0], picked_date_lst[1])[1]
    # Корректно выбирает прошлый месяц
    if picked_date_lst[1] == 1:
        activities = Activities.objects.filter(user=request.user, date=f'{picked_date_lst[0] - 1}-12')
    else:
        activities = Activities.objects.filter(user=request.user, date=f'{picked_date_lst[0]}-{picked_date_lst[1] - 1:0>2}')

    # Создаёт активности прошлого месяца и заносит их в списки
    new_activities = []
    all_activities = []
    new_groups = []
    for activity in activities:
        a = Activities(user=request.user, name=activity.name, date=picked_date, marks='False ' * days,
                       backgroundColor=activity.backgroundColor, number=activity.number, color=activity.color,
                       isGroup=activity.isGroup, isOpen=activity.isOpen, beginDay=0,
                       endDay=days - 1, cellsComments='*|' * days, onOffCells='True ' * days)
        all_activities.append(a)
        if a.isGroup:
            new_groups.append(a)
        else:
            new_activities.append(a)
    Activities.objects.bulk_create(all_activities)

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

    if '/m' in request.META.get('HTTP_REFERER'):
        return redirect('mobile_by_date', picked_date)
    return redirect('by_date', picked_date)


@login_required(login_url='start')
def delete_activity(request):
    get_object_or_404(Activities, pk=int(request.POST['pk'])).delete()
    return HttpResponse()


@login_required(login_url='start')
def global_colors(request, picked_date):
    settings = get_object_or_404(Settings, user=request.user)
    settings.tableHeadColor = request.POST['tableHeadColor']
    settings.tableHeadColorWeekend = request.POST['tableHeadColorWeekend']
    settings.tableHeadTextColor = request.POST['tableHeadTextColor']
    settings.backgroundColor = request.POST['backgroundColor']
    settings.rowColumnLight = request.POST['rowColumnLight']
    settings.save()
    redirect_view = 'mobile_by_date' if '/m' in request.META.get('HTTP_REFERER') else 'by_date'
    return redirect(redirect_view, picked_date)


@login_required(login_url='start')
def create_activity(request, picked_date, is_group):
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
        picked_date_lst = list(map(int, picked_date.split('-')))  # Разделение строки даты на массив года и месяца
        days = monthrange(picked_date_lst[0], picked_date_lst[1])[1]  # Количество дней в месяце
        Activities.objects.create(name=request.POST[inp], date=picked_date, color='#000000', backgroundColor='#ffffff',
                                  marks='False ' * days, onOffCells='True ' * days, number=number, isGroup=is_group,
                                  beginDay=0, endDay=days - 1, isOpen=False, cellsComments='*|' * days, user=request.user)
    redirect_view = 'mobile_by_date' if '/m' in request.META.get('HTTP_REFERER') else 'by_date'
    return redirect(redirect_view, picked_date)


@login_required(login_url='start')
def get_comments(request, picked_date):
    activity, day = get_activity_day(request.POST['checkboxToCheck'], request.user, picked_date)
    return HttpResponse(activity.cellsComments)


@login_required(login_url='start')
def check_cell(request, picked_date):
    activity, day = get_activity_day(request.POST['checkboxToCheck'], request.user, picked_date)
    marks_db = activity.marks.split()
    marks_db[day] = 'False' if marks_db[day] == 'True' else 'True'
    activity.marks = ' '.join(marks_db)
    activity.save(update_fields=['marks'])
    return HttpResponse()


@login_required(login_url='start')
def open_group(request):
    group = Activities.objects.get(pk=int(request.POST['openedGroup']))
    group.isOpen = False if group.isOpen else True
    group.save(update_fields=['isOpen'])
    return HttpResponse()


def get_activity_day(cell, user, picked_date):
    activities = Activities.objects.filter(user=user, date=picked_date)
    activity_day = list(map(int, cell.split('-')))
    return activities[activity_day[0]], activity_day[1]


@login_required(login_url='start')
def delete_all(request, picked_date):
    Activities.objects.filter(user=request.user, date=picked_date).delete()
    return HttpResponse()


def signin(request):
    context = {}
    registration_form = RegisterForm()
    login_form = LoginForm()
    context['registration_form'] = registration_form
    context['login_form'] = login_form
    if request.POST:
        if request.POST['type_form'] == 'registration_form':
            registration_form = RegisterForm(request.POST)
            if registration_form.is_valid():
                user = registration_form.save(commit=False)
                user.username = user.username.lower()
                user.save()
                Settings.objects.create(user=user, backgroundColor='#f0f0f0', tableHeadColorWeekend='#eeb3b3',
                                        tableHeadColor='#e6e4ce', tableHeadTextColor='#000000', showCalendar=False,
                                        showCreateActivity=False, showDeleteAllActivities=False, showDeleteActivity=False,
                                        showCreateActivityGroup=False, enableSortTable=True, enableOpenCloseGroups=False,
                                        onSounds=True, showRowColumnLight=True, showActivityDayLight=True,
                                        rowColumnLight='#e7e7e7', fontFamily='Inter')
                login(request, user)
                return redirect('index')
            else:
                message = 'Аккаунт не создан, некорректные данные!'
                return render(request, 'index.html', {'form': login_form, 'message': message})
        elif request.POST['type_form'] == 'login_form':
            login_form = LoginForm(request.POST)
            if login_form.is_valid():
                username = login_form.cleaned_data['username']
                password = login_form.cleaned_data['password']
                user = authenticate(request, username=username, password=password)
                if user:
                    login(request, user)
                    return redirect('index')
                else:
                    try:
                        User.objects.get(username=login_form.cleaned_data['username'].lower())
                        message = 'Введите логин маленькими буквами!'
                    except User.DoesNotExist:
                        message = 'Некорректные данные!'
                    return render(request, 'index.html', {'form': login_form, 'message': message})
    return render(request, 'index.html', context=context)


@login_required(login_url='start')
def user_logout(request):
    logout(request)
    return redirect('start')
