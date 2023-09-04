from django.shortcuts import render
from .models import Tasks


def start(request):
    if request.POST:
        if request.POST.get('taskText', False):
            time = request.POST['taskTime']
            date = request.POST['taskDate']
            deadline = request.POST['taskDeadline']
            Tasks.objects.create(name=request.POST['taskText'], time=time if time else None,
                                 date=date if date else None, priority=request.POST['taskPriority'],
                                 deadline=deadline if deadline else None, user=request.user)

        if request.POST.get('taskPk', False):
            task = Tasks.objects.get(pk=request.POST['taskPk'])
            task.done = True if request.POST['taskStatus'] == 'on' else False
            task.save()
        if request.POST.get('taskDelete', False):
            Tasks.objects.get(pk=request.POST['taskDelete']).delete()

    tasks = Tasks.objects.filter(user=request.user)
    tasks_done = [t for t in tasks if t.done]
    tasks_not_done = [t for t in tasks if not t.done]
    return render(request, 'test.html', context={'tasks': tasks_not_done, 'tasks_done': tasks_done, 'all_tasks': tasks})
