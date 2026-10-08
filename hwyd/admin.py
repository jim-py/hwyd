from django.contrib import admin
from .models import Activities, ActivitiesConnection, Settings, CustomFieldsUser, Feedback, ScheduledTheme
from django.utils.html import format_html
from django.utils.text import Truncator


@admin.register(ScheduledTheme)
class ScheduledThemeAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'activation_time', 'is_enabled', 'updated_at')
    list_filter = ('is_enabled',)
    search_fields = ('name', 'user__username', 'user__first_name')
    ordering = ('user', 'activation_time')
    readonly_fields = ('created_at', 'updated_at')


class ActivitiesAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'date', 'isGroup']
    list_filter = ['user']
    search_fields = ['name', 'user__username']


admin.site.register(Activities, ActivitiesAdmin)
admin.site.register(ActivitiesConnection)
admin.site.register(Settings)
admin.site.register(CustomFieldsUser)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'category', 'author', 'excerpt']
    list_select_related = ('user',)
    ordering = ('-created_at', '-pk')
    list_per_page = 30
    list_filter = ['category', 'created_at']
    search_fields = ['message', 'user__username', 'user__first_name']
    readonly_fields = ['created_at', 'user', 'full_message']
    fieldsets = (('Обращение', {'fields': ('created_at', 'user', 'category', 'full_message')}),
                 ('Редактирование записи', {'fields': ('message',), 'classes': ('collapse',)}))

    @admin.display(description='Автор')
    def author(self, obj):
        return obj.user.username if obj.user else 'Пользователь удалён / не указан'

    @admin.display(description='Сообщение')
    def excerpt(self, obj):
        return Truncator(obj.message).chars(140)

    @admin.display(description='Полный текст')
    def full_message(self, obj):
        return format_html('<div class="pv-feedback-full">{}</div>', obj.message) if obj else '—'
