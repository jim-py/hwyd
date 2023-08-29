from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from .models import Activities, Settings, ActivitiesConnection
from calendar import monthrange
from datetime import datetime, date
import locale
from .forms import RegisterForm, LoginForm

locale.setlocale(
    category=locale.LC_ALL,
    locale="Russian"
)


@login_required(login_url='start')
def by_date(request, picked_date):
    try:
        redirect_url = 'mobile_by_date' if '/m' in request.META.get('HTTP_REFERER') else 'by_date'
    except TypeError:
        redirect_url = 'by_date'
    # Выбор месяца
    if request.POST.get('chooseDate', False):
        return redirect(redirect_url, picked_date)

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
        groups = activities.filter(isGroup=True)
        groups_ids = [obj.pk for obj in groups]
        activated_groups = [obj.pk for obj in activities.filter(isGroup=True, isOpen=True)]
        settings = Settings.objects.get(user=request.user)

        date_now = datetime.now()
        month_name = date(picked_date_lst[0], picked_date_lst[1], 1).strftime("%B")  # Имя месяца
        days = monthrange(picked_date_lst[0], picked_date_lst[1])[1]  # Количество дней в месяце
        # Отметка нынешнего дня
        today = date_now.day if picked_date_lst[0] == date_now.year and picked_date_lst[1] == date_now.month else -1

        groups_progress = {}
        for group in groups:
            groups_progress[group.pk] = []

        groups_progress_add = {}
        for group in groups:
            groups_progress_add[group.pk] = []

        act_connections = ActivitiesConnection.objects.select_related('group').select_related('activity').filter(user=request.user, activity__date=picked_date)
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

        connections = {}
        for conn in act_connections:
            connections[conn.activity_id] = conn.group_id

        lst_group_conns = {}
        for conn in act_connections:
            lst_group_conns[conn.group_id] = []
        for conn in act_connections:
            lst_group_conns[conn.group_id] += [conn.activity_id]

        group_open = {}
        for conn in act_connections:
            group_open[conn.activity_id] = conn.group.isOpen

        if request.POST:
            print(request.POST)

        if request.POST.get('cell', False):
            if '*' in request.POST['symbols'] or '|' in request.POST['symbols'] or '*' in request.POST['comment'] or '|' in request.POST['comment']:
                return redirect(redirect_url, picked_date)
            activity_day = list(map(int, request.POST['cell'].split('-')))
            activity, day = activities[activity_day[0]], activity_day[1]
            cells_comments = [act.split('*') for act in activity.cellsComments.split('|')]
            cells_comments[day][0] = request.POST['symbols'][:3]
            cells_comments[day][1] = request.POST['comment']
            activity.cellsComments = '|'.join('*'.join(comm) for comm in cells_comments)
            activity.save()
            return redirect(redirect_url, picked_date)

        if request.POST.get('checkboxToCheck', False):
            activity_day = list(map(int, request.POST['checkboxToCheck'].split('-')))
            activity, day = activities[activity_day[0]], activity_day[1]
            marks_db = activity.marks.split()
            marks_db[day] = 'False' if marks_db[day] == 'True' else 'True'
            activity.marks = ' '.join(marks_db)
            activity.save()
            return redirect(redirect_url, picked_date)

        if request.POST.get('data'):
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

        if request.POST.get('openedGroup', False):
            group = Activities.objects.get(pk=int(request.POST['openedGroup']))
            group.isOpen = False if group.isOpen else True
            group.save()
            return redirect(redirect_url, picked_date)

        if request.POST.get('activities[]', False):
            # Сбор активностей в один список
            data = []
            for post in dict(request.POST)['activities[]']:
                data.append(post)
            # Замена порядка активностей
            for activity in activities:
                if activity.name in data:
                    if activity.number != data.index(activity.name):
                        activity.number = data.index(activity.name)
                        activity.save()
            return redirect(redirect_url, picked_date)

        if request.POST.get('activityPk', False):
            activity = Activities.objects.get(pk=int(request.POST['activityPk']))
            if activity.user != request.user:
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
                connection_data = []
                group_id = int(request.POST['activityPk'])
                for post in request.POST:
                    if post.isnumeric():
                        connection_data.append(int(post))
                for connection in ActivitiesConnection.objects.filter(group_id=group_id):
                    connection.activity.number = activity.number - 1
                    connection.activity.save()
                    connection.delete()
                tmp_number = activity.number
                for activity_id in connection_data:
                    for connection in ActivitiesConnection.objects.filter(activity_id=activity_id):
                        connection.delete()
                    connection = ActivitiesConnection.objects.create(user=request.user, group_id=group_id, activity_id=activity_id)
                    connection.activity.number = tmp_number + 1
                    connection.activity.save()
                    tmp_number += 1
            activity.save()
            return redirect(redirect_url, picked_date)

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
                   'lst_group_conns': lst_group_conns, 'group_open': group_open}

        return render(request, 'base.html', context=context)


@login_required(login_url='start')
def start(request):
    current_date = datetime.today()
    return redirect('by_date', f'{current_date.year}-{current_date.month:0>2}')


# def start(request):
#     if request.POST:
#         print(request.POST)
#     context = {'act': Activities.objects.filter(date='2023-09'),
#                'days': [i for i in range(-1, 2)]}
#     return render(request, 'test.html', context=context)


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
    new_groups = []
    for activity in activities:
        a = Activities.objects.create(user=request.user, name=activity.name, date=picked_date, marks='False ' * days, color=activity.color,
                                      backgroundColor=activity.backgroundColor, number=activity.number,
                                      isGroup=activity.isGroup, isOpen=activity.isOpen, beginDay=activity.beginDay,
                                      endDay=activity.endDay, cellsComments='*|' * days, onOffCells='True ' * days)
        if a.isGroup:
            new_groups.append(a)
        else:
            new_activities.append(a)

    # Создаёт словарь пар связей активностей прошлого месяца
    old_dict_pare = {}
    conn = ActivitiesConnection.objects.filter(user=request.user)
    for group in activities.filter(isGroup=True):
        for activity in conn.filter(group=group).select_related('activity'):
            old_dict_pare[activity.activity] = group

    # Создаёт связи новых активностей смотря на пары прошлого месяца
    for new_activity in new_activities:
        for old_activity in old_dict_pare.keys():
            if new_activity.name == old_activity.name:
                for new_group in new_groups:
                    if new_group.name == old_dict_pare[old_activity].name:
                        ActivitiesConnection.objects.create(user=request.user, activity=new_activity, group=new_group)

    if '/m' in request.META.get('HTTP_REFERER'):
        return redirect('mobile_by_date', picked_date)
    return redirect('by_date', picked_date)


@login_required(login_url='start')
def delete_activity(request, pk, picked_date):
    Activities.objects.get(pk=pk).delete()
    if '/m' in request.META.get('HTTP_REFERER'):
        return redirect('mobile_by_date', picked_date)
    return redirect('by_date', picked_date)


@login_required(login_url='start')
def global_colors(request, picked_date):
    settings = Settings.objects.get(user=request.user)
    settings.tableHeadColor = request.POST['tableHeadColor']
    settings.tableHeadColorWeekend = request.POST['tableHeadColorWeekend']
    settings.tableHeadTextColor = request.POST['tableHeadTextColor']
    settings.backgroundColor = request.POST['backgroundColor']
    settings.rowColumnLight = request.POST['rowColumnLight']
    settings.save()
    if '/m' in request.META.get('HTTP_REFERER'):
        return redirect('mobile_by_date', picked_date)
    return redirect('by_date', picked_date)


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
        picked_date_lst = list(map(int, picked_date.split('-')))  # Разделение строки даты на массив года и месяца
        days = monthrange(picked_date_lst[0], picked_date_lst[1])[1]  # Количество дней в месяце
        Activities.objects.create(name=request.POST[inp],
                                  date=picked_date,
                                  color='#000000',
                                  backgroundColor='#ffffff',
                                  marks='False ' * days,
                                  onOffCells='True ' * days,
                                  number=number,
                                  isGroup=is_group,
                                  beginDay=0,
                                  endDay=days - 1,
                                  isOpen=False,
                                  cellsComments='*|' * days,
                                  user=request.user)
    if '/m' in request.META.get('HTTP_REFERER'):
        return redirect('mobile_by_date', picked_date)
    return redirect('by_date', picked_date)


@login_required(login_url='start')
def get_comments(request, picked_date):
    activities = Activities.objects.filter(user=request.user, date=picked_date)
    activity_day = list(map(int, request.POST['cell'].split('-')))
    activity, day = activities[activity_day[0]], activity_day[1]
    return HttpResponse(activity.cellsComments)


@login_required(login_url='start')
def delete_all(request, picked_date):
    for activity in Activities.objects.filter(user=request.user, date=picked_date):
        activity.delete()
    if '/m' in request.META.get('HTTP_REFERER'):
        return redirect('mobile_by_date', picked_date)
    return redirect('by_date', picked_date)


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
                                        showCreateActivityGroup=False, enableSortTable=False, enableOpenCloseGroups=True,
                                        onSounds=True, showRowColumnLight=True, showActivityDayLight=True, rowColumnLight='#e7e7e7')
                login(request, user)
                return redirect('index')
            else:
                return render(request, 'index.html', {'form': registration_form})
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
                return render(request, 'index.html', {'form': login_form})
    return render(request, 'index.html', context=context)


@login_required(login_url='start')
def user_logout(request):
    logout(request)
    return redirect('start')
