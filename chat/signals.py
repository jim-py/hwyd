from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ChatMessage, ChatAttachment
from .storage import delete_photo


@receiver(post_delete, sender=ChatMessage)
def remove_message_photo(sender, instance, **kwargs):
    if instance.photo:
        storage, name = instance.photo.storage, instance.photo.name
        transaction.on_commit(lambda: delete_photo(storage, name))


@receiver(post_delete, sender=ChatAttachment)
def remove_attachment_file(sender, instance, **kwargs):
    storage, name = instance.file.storage, instance.file.name
    transaction.on_commit(lambda: delete_photo(storage, name))
