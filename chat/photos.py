"""Normalize private chat images and silent WebM, preserving transparency."""
import warnings

from django.core.exceptions import ValidationError
from PIL import Image

from general_app.avatar import (normalize_avatar, _normalize_webm, _webm_header,
                                MAX_AVATAR_BYTES, MAX_AVATAR_PIXELS)

MAX_PHOTO_BYTES = MAX_AVATAR_BYTES
MAX_PHOTO_PIXELS = MAX_AVATAR_PIXELS
MAX_ATTACHMENTS = 10
PHOTO_FORMATS = {'JPEG': ('.jpg', 'image/jpeg'), 'PNG': ('.png', 'image/png'),
                 'WEBP': ('.webp', 'image/webp')}


def normalize_photo(upload):
    if upload.size > MAX_PHOTO_BYTES:
        raise ValidationError('Фотография должна быть не больше 5 МиБ.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                image_format = image.format
                if image_format not in PHOTO_FORMATS:
                    raise ValidationError('Разрешены только фотографии JPEG, PNG и WebP.')
                if image.width * image.height > MAX_PHOTO_PIXELS:
                    raise ValidationError('Разрешение фотографии должно быть не больше 20 мегапикселей.')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValidationError('Выберите одну фотографию без анимации.')
            upload.seek(0)
            with Image.open(upload) as image:
                image.verify()
    except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ValidationError('Не удалось прочитать фотографию. Выберите исправное изображение.')
    upload.seek(0)
    # normalize_avatar also strips all metadata and re-encodes decoded pixels.
    # Its video dispatch must never depend on the untrusted original filename.
    upload.name = 'photo' + PHOTO_FORMATS[image_format][0]
    return normalize_avatar(upload)


def normalize_attachment(upload):
    if upload.size > MAX_PHOTO_BYTES:
        raise ValidationError('Каждый файл должен быть не больше 5 МиБ.')
    header = upload.read(4096)
    upload.seek(0)
    if _webm_header(header):
        return _normalize_webm(upload, max_size=1280, preserve_alpha=True), 'video'
    return normalize_photo(upload), 'image'
