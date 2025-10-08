from django.contrib import admin
from .models import Notification, NotificationSeen

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "is_active", "start_at", "end_at", "created_at")
    list_filter = ("is_active", "start_at", "end_at")
    search_fields = ("title", "message")
    filter_horizontal = ("target_users", "target_groups")

@admin.register(NotificationSeen)
class NotificationSeenAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "seen_at")
    search_fields = ("notification__title", "user__username")
