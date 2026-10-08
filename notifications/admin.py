from types import SimpleNamespace

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F
from django.http import Http404, JsonResponse
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone

from my_site.admin_utils import AudienceAdminMixin, StateFilter, DateFilter
from .models import Notification, NotificationSeen


class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = '__all__'
        labels = {'title': 'Заголовок', 'message': 'Содержимое (доверенный HTML)',
                  'is_active': 'Включено', 'start_at': 'Начало публикации', 'end_at': 'Конец публикации',
                  'target_users': 'Пользователи', 'target_groups': 'Группы пользователей'}
        help_texts = {'message': 'HTML отображается как на сайте. Предпросмотр ничего не публикует.',
                      'start_at': 'Пустое значение — доступно сразу.', 'end_at': 'Пустое значение — без срока окончания.',
                      'target_users': 'Если пользователи и группы не выбраны, объявление доступно всем, включая гостей.'}

    def clean(self):
        data = super().clean()
        if data.get('start_at') and data.get('end_at') and data['end_at'] < data['start_at']:
            raise forms.ValidationError('Конец публикации должен быть не раньше начала.')
        return data


@admin.register(Notification)
class NotificationAdmin(AudienceAdminMixin, admin.ModelAdmin):
    form = NotificationForm
    change_form_template = 'admin/productivum/notification_form.html'
    list_display = ('notification_name', 'publication', 'confirmations', 'publication_start', 'publication_end', 'created')
    list_filter = (('is_active', StateFilter), ('start_at', DateFilter), ('end_at', DateFilter))
    search_fields = ('title', 'message')
    filter_horizontal = ('target_users', 'target_groups')
    readonly_fields = ('created', 'publication')
    fieldsets = (('Содержание объявления', {'fields': ('title', 'message')}),
                 ('Публикация на сайте', {'fields': ('is_active', ('start_at', 'end_at'), 'publication', 'created'),
                  'description': 'Это объявление на сайте. Сохранение не отправляет web-push.'}),
                 ('Аудитория', {'fields': ('target_users', 'target_groups')}))
    list_per_page = 30

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(confirmed_count=Count('seen_entries__user_id', distinct=True))

    def get_autocomplete_fields(self, request):
        # Use Django's paginated search where the existing related-model
        # permissions allow it; retain the original selector otherwise.
        return tuple(name for name in ('target_users', 'target_groups')
                     if self.admin_site._registry[self.model._meta.get_field(name).remote_field.model]
                     .has_view_or_change_permission(request))

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), 'title': 'Уведомления на сайте'})

    @admin.display(description='Создано', ordering='created_at')
    def created(self, obj):
        return obj.created_at

    @admin.display(description='Начало публикации', ordering='start_at')
    def publication_start(self, obj):
        return obj.start_at

    @admin.display(description='Конец публикации', ordering='end_at')
    def publication_end(self, obj):
        return obj.end_at

    @admin.display(description='Объявление')
    def notification_name(self, obj):
        return obj.title or f'Объявление #{obj.pk}'

    @admin.display(description='Публикация')
    def publication(self, obj):
        now = timezone.now()
        if not obj.is_active:
            return 'Выключено'
        if obj.start_at and obj.start_at > now:
            return 'Запланировано'
        if obj.end_at and obj.end_at < now:
            return 'Срок истёк'
        return 'Доступно сейчас'

    @admin.display(description='Подтвердили / закрыли', ordering='confirmed_count')
    def confirmations(self, obj):
        return self.audience_link(obj, obj.confirmed_count)

    def audience_rows(self, request, obj):
        return (NotificationSeen.objects.filter(notification=obj).annotate(timestamp=F('seen_at')),
                'Подтвердили / закрыли (авторизованные пользователи)')

    def get_urls(self):
        return [path('preview/', self.admin_site.admin_view(self.preview), name='notifications_notification_preview'),
                path('<int:object_id>/preview/', self.admin_site.admin_view(self.preview),
                     name='notifications_notification_object_preview')] + super().get_urls()

    def preview(self, request, object_id=None):
        if request.method not in ('GET', 'POST'):
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['GET', 'POST'])
        obj = self.get_object(request, object_id) if object_id else None
        if object_id and obj is None:
            raise Http404
        if request.method == 'POST':
            allowed = self.has_change_permission(request, obj) if obj else self.has_add_permission(request)
        else:
            allowed = obj is not None and self.has_view_or_change_permission(request, obj)
        if not allowed:
            raise PermissionDenied
        request.admin_preview = True
        title = request.POST.get('title', '') if request.method == 'POST' else obj.title
        message = request.POST.get('message', '') if request.method == 'POST' else obj.message
        if len(title) > 200 or len(message) > 100_000:
            return JsonResponse({'error': 'Заголовок — до 200 символов, предпросмотр HTML — до 100 000.'}, status=400)
        html = render_to_string('admin/productivum/notification_preview.html', {
            'unread_notification': SimpleNamespace(title=title, message=message, id='preview'),
            'notification_preview': True,
        })
        return JsonResponse({'html': html})

    def render_change_form(self, request, context, *args, **kwargs):
        obj = kwargs.get('obj')
        context['title'] = 'Новое уведомление' if obj is None else f'Уведомление: {obj.title or obj.pk}'
        context['preview_url'] = reverse('admin:notifications_notification_object_preview', args=[obj.pk]) if obj else reverse('admin:notifications_notification_preview')
        context['preview_method'] = 'POST' if (self.has_change_permission(request, obj) if obj else self.has_add_permission(request)) else 'GET'
        return super().render_change_form(request, context, *args, **kwargs)


@admin.register(NotificationSeen)
class NotificationSeenAdmin(admin.ModelAdmin):
    list_display = ('notification', 'user', 'seen_at')
    list_select_related = ('notification', 'user')
    search_fields = ('notification__title', 'user__username')
