from django.contrib import admin
from .models import Activities, ActivitiesConnection, Settings, CustomFieldsUser, Feedback, ScheduledTheme


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
    list_display = ['created_at', 'category', 'user', 'message']
    list_filter = ['category', 'created_at']
    search_fields = ['message', 'user__username', 'user__first_name']
    readonly_fields = ['created_at', 'user']
