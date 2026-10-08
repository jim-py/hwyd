from calendar import monthrange

from django import forms
from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone


class HabitRangeForm(forms.Form):
    start = forms.DateField(label='С', widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='По', widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        if 'start' in data and 'end' in data:
            days = (data['end'] - data['start']).days
            if days < 0:
                raise forms.ValidationError('Конец периода должен быть не раньше начала.')
            if days >= 366:
                raise forms.ValidationError('Выберите не больше 366 календарных дней.')
        return data


class ProductivumAdminSite(AdminSite):
    site_header = 'Productivum'
    site_title = 'Productivum · Управление'
    index_title = 'Обзор'
    index_template = 'admin/productivum/index.html'

    def get_urls(self):
        return [path('habit-statistics/', self.admin_view(self.habit_statistics),
                     name='habit_statistics')] + super().get_urls()

    def index(self, request, extra_context=None):
        from notifications.models import Notification
        from hwyd.models import Feedback, Activities
        from general_app.models import Guide
        cards = []
        latest = []
        can_feedback = False
        for model, title, description in (
            (Notification, 'Уведомления', 'Объявления на сайте, аудитория и подтверждения.'),
            (Feedback, 'Обратная связь', 'Обращения пользователей, новые сверху.'),
            (Guide, 'Гайды обучения', 'Предпросмотр, версии и реальные открытия.'),
            (Activities, 'Отметки привычек', 'Текущее состояние клеток по календарным датам.'),
        ):
            model_admin = self._registry[model]
            if not model_admin.has_view_or_change_permission(request):
                continue
            prefix = f'{model._meta.app_label}_{model._meta.model_name}'
            card = {'title': title, 'description': description,
                    'url': reverse('admin:habit_statistics' if model == Activities else f'admin:{prefix}_changelist')}
            if model != Activities:
                card['count'] = model.objects.count()
                if model_admin.has_add_permission(request):
                    card['add_url'] = reverse(f'admin:{prefix}_add')
            cards.append(card)
            if model == Feedback:
                can_feedback = True
                latest = model.objects.select_related('user').order_by('-created_at', '-pk')[:5]
        return super().index(request, {**(extra_context or {}), 'priority_cards': cards,
                                       'latest_feedback': latest, 'can_feedback': can_feedback})

    def habit_statistics(self, request):
        from hwyd.models import Activities
        from hwyd.admin_statistics import habit_statistics
        if not self._registry[Activities].has_view_or_change_permission(request):
            raise PermissionDenied
        today = timezone.localdate()
        start = today.replace(day=1)
        end = today.replace(day=monthrange(today.year, today.month)[1])
        form = HabitRangeForm(request.GET if request.GET else None,
                             initial={'start': start.isoformat(), 'end': end.isoformat()})
        result = None
        if not form.is_bound:
            result = habit_statistics(start, end)
        elif form.is_valid():
            result = habit_statistics(form.cleaned_data['start'], form.cleaned_data['end'])
        request.current_app = self.name
        return TemplateResponse(request, 'admin/productivum/habit_statistics.html', {
            **self.each_context(request), 'title': 'Ежедневные отметки привычек',
            'form': form, 'stats': result, 'month_start': start.isoformat(), 'month_end': end.isoformat(),
            'today': today.isoformat(),
        })
