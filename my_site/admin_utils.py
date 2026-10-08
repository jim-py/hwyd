from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from urllib.parse import urlencode
from django.contrib import admin


class LocalizedFilter:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = {'is_active': 'Включено', 'version': 'Версия', 'created_at': 'Создано',
                      'start_at': 'Начало публикации', 'end_at': 'Конец публикации'}.get(self.field.name, self.title)


class StateFilter(LocalizedFilter, admin.BooleanFieldListFilter):
    pass


class DateFilter(LocalizedFilter, admin.DateFieldListFilter):
    pass


class VersionFilter(LocalizedFilter, admin.AllValuesFieldListFilter):
    pass


class AudienceAdminMixin:
    """No names in changelist rows: fetch at most ten on hover or keyboard focus."""
    def get_urls(self):
        name = f'{self.opts.app_label}_{self.opts.model_name}_audience'
        return [path('<int:object_id>/audience/', self.admin_site.admin_view(self.audience),
                     name=name)] + super().get_urls()

    def audience_link(self, obj, count, **params):
        url = reverse(f'admin:{self.opts.app_label}_{self.opts.model_name}_audience', args=[obj.pk])
        if params:
            url += '?' + urlencode(params)
        return format_html('<span class="pv-audience"><a href="{}" data-audience-url="{}" '
                           'aria-label="Список пользователей: {}">{}</a>'
                           '<span class="pv-tooltip" role="status" hidden></span></span>', url, url, count, count)

    def audience(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied
        rows, label = self.audience_rows(request, obj)
        query = request.GET.get('q', '')[:100]
        if query:
            rows = rows.filter(user__username__icontains=query)
        rows = rows.order_by('user__username', 'pk').values('user__username', 'timestamp')
        if request.GET.get('sample') == '1':
            return JsonResponse({'names': [item['user__username'] for item in rows[:10]], 'total': rows.count()})
        page = Paginator(rows, 50).get_page(request.GET.get('page'))
        params = request.GET.copy()
        params.pop('page', None)
        request.current_app = self.admin_site.name
        return TemplateResponse(request, 'admin/productivum/audience.html', {
            **self.admin_site.each_context(request), 'title': f'{obj}: {label}', 'object': obj,
            'page': page, 'query': query, 'params': params.urlencode(), 'label': label,
            'kind': request.GET.get('kind', ''), 'version': request.GET.get('version', ''),
            'changelist_url': reverse(f'admin:{self.opts.app_label}_{self.opts.model_name}_changelist'),
        })
