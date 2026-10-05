"""Site-wide framing permissions, with a strict exception for the admin."""
from django.conf import settings


def set_frame_ancestors(response, directive):
    # A CSP header can contain multiple policies. Update each one, preserving
    # its other directives, so stale policies cannot conflict with this rule.
    policies = []
    for policy in response.get('Content-Security-Policy', '').split(','):
        directives = [item.strip() for item in policy.split(';')
                      if item.strip() and item.strip().split()[0].lower() != 'frame-ancestors']
        policies.append('; '.join([*directives, directive]))
    response['Content-Security-Policy'] = ', '.join(policies)


class SiteFramePolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # path_info also works when the application is mounted under a prefix.
        # Protect redirects and missing URLs under /admin/, not just admin views.
        if request.path_info == '/admin' or request.path_info.startswith('/admin/'):
            response['X-Frame-Options'] = 'DENY'
            directive = "frame-ancestors 'none'"
        else:
            if response.has_header('X-Frame-Options'):
                del response['X-Frame-Options']
            directive = "frame-ancestors 'self' " + ' '.join(settings.HABITUS_FRAME_ORIGINS)
        set_frame_ancestors(response, directive.strip())
        return response
