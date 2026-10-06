from django.conf import settings
from django.db import models
from pathlib import Path
from uuid import uuid4

from .storage import ChatPhotoStorage


MESSAGE_MAX_LENGTH = 2000


def chat_photo_path(instance, filename):
    return f'{uuid4().hex}{Path(filename).suffix.lower()}'


class ChatMessage(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.CharField(max_length=MESSAGE_MAX_LENGTH, blank=True)
    photo = models.FileField('Фотография', upload_to=chat_photo_path,
                             storage=ChatPhotoStorage(), blank=True)
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


class ChatAttachment(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=chat_photo_path, storage=ChatPhotoStorage())
    kind = models.CharField(max_length=5, choices=[('image', 'Фотография'), ('video', 'WebM')])
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['message', 'position'], name='chat_attachment_position')]
