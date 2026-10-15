"""Canonical redirects use the server's scheme, never client forwarded headers."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponsePermanentRedirect

from general_app.seo import public_origin


class SearchEnginePolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = None
        if settings.CANONICAL_REDIRECTS_ENABLED:
            origin = public_origin()
            if not origin.startswith('https://'):
                raise ImproperlyConfigured('Canonical redirects require an HTTPS PUBLIC_SITE_ORIGIN.')
            # get_host validates ALLOWED_HOSTS. Proxy TLS must already be reflected
            # in the trusted WSGI/ASGI scheme supplied by the hosting server.
            host = request.get_host().lower()
            legacy_home = request.path_info in ('/home', '/home/')
            if not request.is_secure() or host != origin.removeprefix('https://').lower() or legacy_home:
                path = request.get_full_path()
                if legacy_home:
                    query = request.META.get('QUERY_STRING', '')
                    path = '/' + ('?' + query if query else '')
                response = HttpResponsePermanentRedirect(origin + path)
        if response is None:
            response = self.get_response(request)
        if request.path_info.rstrip('/') == '/home/entry':
            response['X-Robots-Tag'] = 'noindex, follow'
        return response
