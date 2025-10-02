from django.contrib import admin
from .models import Activities, ActivitiesConnection, Settings, CustomFieldsUser


class ActivitiesAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'date', 'isGroup']
    list_filter = ['user']
    search_fields = ['name', 'user__username']


admin.site.register(Activities, ActivitiesAdmin)
admin.site.register(ActivitiesConnection)
admin.site.register(Settings)
admin.site.register(CustomFieldsUser)
