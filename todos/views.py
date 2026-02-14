import datetime
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import generic
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from .models import Todo
from django.http import JsonResponse
import json
from datetime import date


class IndexView(LoginRequiredMixin, generic.ListView):
    template_name = 'todos/index.html'
    context_object_name = 'todo_all'
    login_url = '/home/entry/'

    def get_queryset(self):
        user = self.request.user
        qs = Todo.objects.filter(user=user)

        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')

        if year and month and day:
            try:
                selected_date = date(year, month, day)
                qs = qs.filter(task_date=selected_date)
            except ValueError:
                pass  # некорректная дата — возвращаем все задачи

        return qs.order_by('-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')

        if year and month and day:
            context['selected_date'] = date(year, month, day)
        else:
            context['selected_date'] = None

        return context


def redirect_to_today(request):
    today = date.today()
    # Форматируем месяц и день с ведущим нулём
    month = f"{today.month:02d}"
    day = f"{today.day:02d}"
    return redirect('todos:index_by_date',
                    year=today.year, month=month, day=day)


@require_POST
def add(request):
    response_data = {'success': False}

    try:
        data = json.loads(request.body)
        title = data['title']
        task_date_str = data.get('task_date')

        if not task_date_str:
            raise ValueError("Дата задачи не указана")

        task_date = datetime.datetime.strptime(task_date_str, '%Y-%m-%d').date()

        new_todo = Todo.objects.create(
            user=request.user,
            title=title,
            task_date=task_date
        )

        response_data = {
            'id': new_todo.id,
            'title': new_todo.title,
            'success': True,
        }
    except Exception as e:
        response_data['error'] = str(e)

    return JsonResponse(response_data)


@require_POST
def update(request, todo_id):
    todo = get_object_or_404(Todo, pk=todo_id, user=request.user)
    try:
        # Принимаем и обрабатываем JSON данные.
        data = json.loads(request.body)
        is_completed = data.get('isCompleted', False)

        # Устанавливаем новое значение и сохраняем объект.
        todo.checked = is_completed
        todo.save()

        # Возвращаем успешный ответ.
        return JsonResponse({'success': True, 'isCompleted': is_completed})

    except ValidationError as e:
        # Обработка ошибки валидации данных.
        return JsonResponse({'success': False, 'error': str(e)})


@require_POST
def delete(request, todo_id):
    todo = get_object_or_404(Todo, pk=todo_id, user=request.user)
    try:
        todo.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_POST
def load_todos_from_json(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)  # парсим JSON

            user = request.user  # текущий пользователь
            # Если нужно тестово назначить конкретного пользователя, можно так:
            # user = get_user_model().objects.get(username='testuser')

            todos_created = []

            for item in data:
                todo = Todo.objects.create(
                    user=user,
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    task_date=item.get("task_date"),
                    checked=False
                )
                todos_created.append({
                    "id": todo.id,
                    "title": todo.title,
                    "description": todo.description,
                    "task_date": str(todo.task_date)
                })

            return JsonResponse({"status": "success", "created": todos_created}, status=201)

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    else:
        return JsonResponse({"status": "error", "message": "POST method required"}, status=405)
```
