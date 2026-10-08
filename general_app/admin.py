from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, OuterRef, Subquery, IntegerField, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from my_site.admin_utils import AudienceAdminMixin, StateFilter, VersionFilter
from .guides import GUIDE_MODULES
from .models import Guide, UserGuideProgress, GuideOpening


class GuideForm(forms.ModelForm):
    class Meta:
        model = Guide
        fields = '__all__'
        labels = {'slug': 'Код сценария (slug)', 'title': 'Название', 'version': 'Версия', 'is_active': 'Включён'}
        help_texts = {'slug': 'Сценарий должен входить в проверенный реестр модулей. Сейчас доступен main_toolbar.',
                      'version': 'Новая версия повторно предлагает обучение. Старые открытия сохраняются отдельно.'}

    def clean_version(self):
        version = self.cleaned_data['version']
        if version < 1:
            raise forms.ValidationError('Версия должна быть не меньше 1.')
        return version


@admin.register(Guide)
class GuideAdmin(AudienceAdminMixin, admin.ModelAdmin):
    form = GuideForm
    change_form_template = 'admin/productivum/guide_form.html'
    list_display = ('guide_name', 'guide_slug', 'guide_version', 'enabled', 'opened', 'acknowledged', 'preview_link')
    list_filter = (('is_active', StateFilter), ('version', VersionFilter))
    search_fields = ('title', 'slug')
    readonly_fields = ('created', 'preview_link')
    fieldsets = (('Сценарий обучения', {'fields': ('title', 'slug', 'version', 'is_active', 'preview_link', 'created')}),)
    list_per_page = 30

    @admin.display(description='Создано')
    def created(self, obj):
        return obj.created_at

    @admin.display(description='Название', ordering='title')
    def guide_name(self, obj):
        return obj.title

    @admin.display(description='Код сценария', ordering='slug')
    def guide_slug(self, obj):
        return obj.slug

    @admin.display(description='Версия', ordering='version')
    def guide_version(self, obj):
        return obj.version

    @admin.display(description='Включён', boolean=True, ordering='is_active')
    def enabled(self, obj):
        return obj.is_active

    def get_queryset(self, request):
        def count(query):
            return Coalesce(Subquery(query.order_by().values('guide_id').annotate(n=Count('user_id', distinct=True)).values('n'),
                                     output_field=IntegerField()), Value(0))
        openings = GuideOpening.objects.filter(guide_id=OuterRef('pk'), version=OuterRef('version'))
        progress = UserGuideProgress.objects.filter(guide_id=OuterRef('pk'), version_seen=OuterRef('version'), viewed=True)
        return super().get_queryset(request).annotate(opened_count=count(openings), confirmed_count=count(progress))

    @admin.display(description='Открыли текущую версию', ordering='opened_count')
    def opened(self, obj):
        return self.audience_link(obj, obj.opened_count, kind='opened', version=obj.version)

    @admin.display(description='Подтвердили / закрыли текущую версию', ordering='confirmed_count')
    def acknowledged(self, obj):
        return self.audience_link(obj, obj.confirmed_count, kind='acknowledged', version=obj.version)

    @admin.display(description='Предпросмотр')
    def preview_link(self, obj):
        if not obj.pk:
            return 'Сохраните код сценария, чтобы открыть предпросмотр.'
        return format_html('<a href="{}">Смотреть гайд и версии</a>', reverse('admin:general_app_guide_preview', args=[obj.pk]))

    def audience_rows(self, request, obj):
        try:
            version = int(request.GET.get('version', obj.version))
            if not 1 <= version <= 2_147_483_647:
                raise ValueError
        except ValueError:
            raise Http404
        kind = request.GET.get('kind', 'opened')
        if kind == 'opened':
            rows = GuideOpening.objects.filter(guide=obj, version=version).annotate(timestamp=F('opened_at'))
            label = f'Открыли версию {version}'
        elif kind == 'acknowledged':
            rows = UserGuideProgress.objects.filter(guide=obj, version_seen=version, viewed=True).annotate(timestamp=F('viewed_at'))
            label = f'Подтвердили / закрыли версию {version} (последнее состояние)'
        else:
            raise Http404
        return rows, label

    def get_urls(self):
        return [path('<int:object_id>/preview/', self.admin_site.admin_view(self.preview),
                     name='general_app_guide_preview')] + super().get_urls()

    def preview(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        request.admin_preview = True
        history = {item['version']: {'version': item['version'], 'openings': item['n'], 'confirmations': 0}
                   for item in GuideOpening.objects.filter(guide=obj).values('version').annotate(n=Count('user_id', distinct=True))}
        for item in UserGuideProgress.objects.filter(guide=obj, viewed=True).values('version_seen').annotate(n=Count('user_id', distinct=True)):
            history.setdefault(item['version_seen'], {'version': item['version_seen'], 'openings': 0})['confirmations'] = item['n']
        history.setdefault(obj.version, {'version': obj.version, 'openings': 0, 'confirmations': 0})
        for item in history.values():
            item['open_url'] = reverse('admin:general_app_guide_audience', args=[obj.pk]) + f'?kind=opened&version={item["version"]}'
            item['confirmed_url'] = reverse('admin:general_app_guide_audience', args=[obj.pk]) + f'?kind=acknowledged&version={item["version"]}'
        request.current_app = self.admin_site.name
        return TemplateResponse(request, 'admin/productivum/guide_preview.html', {
            **self.admin_site.each_context(request), 'title': f'Предпросмотр: {obj.title}',
            'guide': obj, 'supported': obj.slug in GUIDE_MODULES,
            'versions': sorted(history.values(), key=lambda row: row['version'], reverse=True),
        })


@admin.register(UserGuideProgress)
class UserGuideProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'guide', 'version_seen', 'viewed', 'viewed_at')
    list_select_related = ('user', 'guide')
    search_fields = ('user__username', 'guide__title')
    list_filter = ('viewed', 'guide')


@admin.register(GuideOpening)
class GuideOpeningAdmin(admin.ModelAdmin):
    list_display = ('guide', 'version', 'user', 'opened_at')
    list_select_related = ('guide', 'user')
    search_fields = ('guide__title', 'user__username')
    list_filter = ('version', 'guide')
    readonly_fields = ('guide', 'version', 'user', 'opened_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
