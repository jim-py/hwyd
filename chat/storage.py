"""Chat uploads have no public media URL; views enforce chat authentication."""
import logging

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property


@deconstructible
class ChatPhotoStorage(FileSystemStorage):
    @cached_property
    def base_location(self):
        return settings.CHAT_PHOTO_ROOT

    @cached_property
    def base_url(self):
        return None

    def _clear_cached_properties(self, setting, **kwargs):
        super()._clear_cached_properties(setting, **kwargs)
        if setting == 'CHAT_PHOTO_ROOT':
            self.__dict__.pop('base_location', None)
            self.__dict__.pop('location', None)


def delete_photo(storage, name):
    if name:
        try:
            storage.delete(name)
        except OSError:
            logging.getLogger(__name__).warning('Could not remove chat photo', exc_info=True)
