"""Local extensions of installed admin registrations."""

from django.contrib import admin
from django_celery_beat.admin import (
    ClockedScheduleAdmin, CrontabScheduleAdmin, IntervalScheduleAdmin,
    PeriodicTaskInline, SolarScheduleAdmin,
)
from django_celery_beat.models import (
    ClockedSchedule, CrontabSchedule, IntervalSchedule, SolarSchedule,
)


class RelatedScheduleTaskInline(PeriodicTaskInline):
    def get_queryset(self, request):
        # The inline's original-object label calls PeriodicTask.__str__, which
        # reads these four schedule fields. Match PeriodicTaskAdmin's joins.
        return super().get_queryset(request).select_related('interval', 'crontab', 'solar', 'clocked')


class ProductivumClockedScheduleAdmin(ClockedScheduleAdmin):
    inlines = [RelatedScheduleTaskInline]


class ProductivumCrontabScheduleAdmin(CrontabScheduleAdmin):
    inlines = [RelatedScheduleTaskInline]


class ProductivumIntervalScheduleAdmin(IntervalScheduleAdmin):
    inlines = [RelatedScheduleTaskInline]


class ProductivumSolarScheduleAdmin(SolarScheduleAdmin):
    inlines = [RelatedScheduleTaskInline]


def register_schedule_admins():
    # Called after AdminConfig's autodiscovery; preserve each package admin's
    # fields, widgets, permissions and read-only inline behavior.
    for model, admin_class in (
        (ClockedSchedule, ProductivumClockedScheduleAdmin),
        (CrontabSchedule, ProductivumCrontabScheduleAdmin),
        (IntervalSchedule, ProductivumIntervalScheduleAdmin),
        (SolarSchedule, ProductivumSolarScheduleAdmin),
    ):
        admin.site.unregister(model)
        admin.site.register(model, admin_class)
