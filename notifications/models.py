from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import Group

class Notification(models.Model):
    title = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    target_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="target_notifications"
    )
    target_groups = models.ManyToManyField(Group, blank=True, related_name="target_notifications")

    class Meta:
        ordering = ("-created_at",)

    def is_current(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.start_at and self.start_at > now:
            return False
        if self.end_at and self.end_at < now:
            return False
        return True

    def __str__(self):
        return self.title or f"Notification #{self.pk}"


class NotificationSeen(models.Model):
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="seen_entries"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_seen"
    )
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("notification", "user")

    def __str__(self):
        return f"{self.user} saw {self.notification} at {self.seen_at}"
