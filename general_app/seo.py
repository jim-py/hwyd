"""Canonical public addresses, independent of request headers and user data."""
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse


PUBLIC_PAGE_NAMES = ('home', 'about', 'habitus_guide', 'habit_tracking_guide')


def public_origin():
    origin = settings.PUBLIC_SITE_ORIGIN.rstrip('/')
    parts = urlsplit(origin)
    if (parts.scheme not in ('https', 'http') or not parts.netloc or parts.path
            or parts.query or parts.fragment or parts.username is not None or parts.password is not None):
        raise ImproperlyConfigured('PUBLIC_SITE_ORIGIN must be an HTTP(S) origin without a path or credentials.')
    return origin


def canonical_url(page_name):
    return public_origin() + reverse(page_name)
