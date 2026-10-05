"""The frame policy for the tracker, login page and landing page."""
from functools import wraps

from django.conf import settings


def local_dashboard_frame_ancestors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        frame_ancestors = "frame-ancestors 'self' " + " ".join(settings.HABITUS_FRAME_ORIGINS)
        # A CSP header can contain multiple policies. Replace the directive in
        # each policy: otherwise an older, stricter policy still blocks framing.
        policies = []
        for policy in response.get('Content-Security-Policy', '').split(','):
            directives = [directive.strip() for directive in policy.split(';')
                          if directive.strip() and
                          directive.strip().split()[0].lower() != 'frame-ancestors']
            policies.append('; '.join([*directives, frame_ancestors.strip()]))
        response['Content-Security-Policy'] = ', '.join(policies)
        return response

    return wrapped
