from django.conf import settings
from django.db import models


MESSAGE_MAX_LENGTH = 2000


class ChatMessage(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.CharField(max_length=MESSAGE_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    reply_to = models.ForeignKey('self', null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name='replies')
    edited_at = models.DateTimeField(null=True, blank=True)
    # Retain the row/ID for replies and read cursors, but erase deleted text.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']


class ChatReadState(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # A cursor rather than a FK: deleting an old message must not reset reads.
    last_read_message_id = models.PositiveBigIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
