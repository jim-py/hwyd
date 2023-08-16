from django.http import HttpResponse
from django.shortcuts import render, redirect
from .models import Activities, Settings, ActivitiesConnection
from calendar import monthrange
from datetime import datetime, date
import locale

locale.setlocale(
    category=locale.LC_ALL,
    locale="Russian"
)


def by_date(request, picked_date):
    # Выбор месяца
    if request.POST.get('chooseDate', False):
        return redirect('by_date', request.POST['chooseDate'])

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
        activities = Activities.objects.filter(date=picked_date)
        groups = activities.filter(isGroup=True)
        groups_ids = [obj.pk for obj in groups]
        activated_groups = [obj.pk for obj in activities.filter(isGroup=True, isOpen=True)]
        settings = Settings.objects.get(pk=1)

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

        for group in groups:
            activities_connection = ActivitiesConnection.objects.filter(group=group)
            for day in range(days):
                tmp = []
                for connection in activities_connection:
                    if connection.activity.beginDay <= day <= connection.activity.endDay:
                        tmp.append(connection.activity.marks.split()[day])
                if len(tmp) == 0:
                    groups_progress[group.pk] += [-1]
                    groups_progress_add[group.pk] += [0.0]
                    continue
                groups_progress[group.pk] += [tmp.count('True') / len(tmp) * 100]
                groups_progress_add[group.pk] += [1 / len(tmp) * 100]

        if request.POST:
            print(request.POST)

        if request.POST.get('cell', False):
            activity_day = list(map(int, request.POST['cell'].split('-')))
            activity, day = activities[activity_day[0]], activity_day[1]
            cells_comments = [act.split('*') for act in activity.cellsComments.split('|')]
            cells_comments[day][0] = request.POST['symbols'][:3]
            cells_comments[day][1] = request.POST['comment']
            activity.cellsComments = '|'.join('*'.join(comm) for comm in cells_comments)
            activity.save()
            return redirect('by_date', picked_date)

        if request.POST.get('checkboxToCheck', False):
            activity_day = list(map(int, request.POST['checkboxToCheck'].split('-')))
            activity, day = activities[activity_day[0]], activity_day[1]
            marks_db = activity.marks.split()
            marks_db[day] = 'False' if marks_db[day] == 'True' else 'True'
            activity.marks = ' '.join(marks_db)
            activity.save()
            return redirect('by_date', picked_date)

        if request.POST.get('data', False):
            lst = list(True if i == 'true' else False for i in dict(request.POST)['data'][0].split(','))
            settings.showCalendar = lst[0]
            settings.showCreateActivity = lst[1]
            settings.showDeleteActivity = lst[2]
            settings.showDeleteAllActivities = lst[3]
            settings.showCreateActivityGroup = lst[4]
            if request.POST['radioSettings'] == 'sort':
                settings.enableSortTable = True
                settings.enableOpenCloseGroups = False
            else:
                settings.enableSortTable = False
                settings.enableOpenCloseGroups = True
            settings.save()
            return redirect('by_date', picked_date)

        if request.POST.get('openedGroup', False):
            group = Activities.objects.get(pk=int(''.join(i for i in request.POST['openedGroup'] if i.isdigit())))
            group.isOpen = False if group.isOpen else True
            group.save()
            return redirect('by_date', picked_date)

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
            return redirect('by_date', picked_date)

        if request.POST.get('activityPk', False):
            activity = Activities.objects.get(pk=int(request.POST['activityPk']))
            activity.name = request.POST['activityName']
            activity.beginDay = int(request.POST['beginDay']) - 1 if -1 < int(request.POST['beginDay']) - 1 < days else 0
            activity.endDay = int(request.POST['endDay']) - 1 if -1 < int(request.POST['endDay']) - 1 < days else days - 1
            activity.backgroundColor = request.POST['backgroundColor']
            activity.color = request.POST['color']

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
                connection = ActivitiesConnection.objects.create(group_id=group_id, activity_id=activity_id)
                connection.activity.number = tmp_number + 1
                connection.activity.save()
                tmp_number += 1
            activity.save()
            return redirect('by_date', picked_date)

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

        context = {'range_activities': activities, 'range_days': [i for i in range(-1, days)],
                   'weekends': weekends, 'cellsToClick': activated_cells, 'date': picked_date,
                   'settings': settings, 'progress': progress_activities, 'today': today, 'month_name': month_name,
                   'year': picked_date_lst[0], 'groups_ids': groups_ids, 'days': days, 'groupsToClick': activated_groups,
                   'groups_progress': groups_progress, 'groups_progress_add': groups_progress_add}

        return render(request, 'base.html', context=context)


def start(request):
    current_date = datetime.today()
    return redirect('by_date', f'{current_date.year}-{current_date.month:0>2}')


# def start(request):
#     if request.POST:
#         print(request.POST)
#     context = {'act': Activities.objects.filter(date='2023-09'),
#                'days': [i for i in range(-1, 2)]}
#     return render(request, 'test.html', context=context)


def create_last_activities(request, picked_date):
    picked_date_lst = list(map(int, picked_date.split('-')))
    days = monthrange(picked_date_lst[0], picked_date_lst[1])[1]

    # Корректно выбирает прошлый месяц
    if picked_date_lst[1] == 1:
        activities = Activities.objects.filter(date=f'{picked_date_lst[0] - 1}-12')
    else:
        activities = Activities.objects.filter(date=f'{picked_date_lst[0]}-{picked_date_lst[1] - 1:0>2}')

    # Создаёт активности прошлого месяца и заносит их в списки
    new_activities = []
    new_groups = []
    for activity in activities:
        a = Activities.objects.create(name=activity.name, date=picked_date, marks='False ' * days, color=activity.color,
                                      backgroundColor=activity.backgroundColor, number=activity.number,
                                      isGroup=activity.isGroup, isOpen=activity.isOpen, beginDay=activity.beginDay,
                                      endDay=activity.endDay, cellsComments='*|' * days)
        if a.isGroup:
            new_groups.append(a)
        else:
            new_activities.append(a)

    # Создаёт словарь пар связей активностей прошлого месяца
    old_dict_pare = {}
    conn = ActivitiesConnection.objects.all()
    for group in activities.filter(isGroup=True):
        for activity in conn.filter(group=group):
            old_dict_pare[activity.activity] = group

    # Создаёт связи новых активностей смотря на пары прошлого месяца
    for new_activity in new_activities:
        for old_activity in old_dict_pare.keys():
            if new_activity.name == old_activity.name:
                for new_group in new_groups:
                    if new_group.name == old_dict_pare[old_activity].name:
                        ActivitiesConnection.objects.create(activity=new_activity, group=new_group)

    return redirect('by_date', picked_date)


def delete_activity(request, pk, picked_date):
    Activities.objects.get(pk=pk).delete()
    return redirect('by_date', picked_date)


def global_colors(request, picked_date):
    settings = Settings.objects.get(pk=1)
    settings.tableHeadColor = request.POST['tableHeadColor']
    settings.tableHeadColorWeekend = request.POST['tableHeadColorWeekend']
    settings.tableHeadTextColor = request.POST['tableHeadTextColor']
    settings.backgroundColor = request.POST['backgroundColor']
    settings.save()
    return redirect('by_date', picked_date)


def create_activity(request, picked_date, is_group):
    inp = 'createActivityGroupInput' if is_group else 'createActivityInput'
    try:
        Activities.objects.get(name=request.POST[inp], date=picked_date)
    except Activities.DoesNotExist:
        picked_date_lst = list(map(int, picked_date.split('-')))  # Разделение строки даты на массив года и месяца
        days = monthrange(picked_date_lst[0], picked_date_lst[1])[1]  # Количество дней в месяце
        Activities.objects.create(name=request.POST[inp],
                                  date=picked_date,
                                  color='#000000',
                                  backgroundColor='#ffffff',
                                  marks='False ' * days,
                                  number=100,
                                  isGroup=is_group,
                                  beginDay=0,
                                  endDay=days - 1,
                                  isOpen=False,
                                  cellsComments='*|' * days)
    return redirect('by_date', picked_date)


def get_comments(request, picked_date):
    activities = Activities.objects.filter(date=picked_date)
    activity_day = list(map(int, request.POST['cell'].split('-')))
    activity, day = activities[activity_day[0]], activity_day[1]
    return HttpResponse(activity.cellsComments)


def delete_all(request, picked_date):
    for activity in Activities.objects.filter(date=picked_date):
        activity.delete()
    return redirect('by_date', picked_date)
