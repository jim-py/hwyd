from django.contrib import admin
from .models import Activities, ActivitiesConnection, Settings

admin.site.register(Activities)
admin.site.register(ActivitiesConnection)
admin.site.register(Settings)
