"""Explicit, request-scoped presentation reads; authentication never changes."""
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import F
from django.http import JsonResponse


def get_viewed_user(request):
    if not hasattr(request, '_habitus_viewed_user'):
        user = request.user
        target = request.GET.get('view_as')
        if user.is_authenticated and user.is_superuser and target:
            try:
                model = get_user_model()
                pk = model._meta.pk.to_python(target)
                user = model.objects.filter(pk=pk).first() or user
            except (ValidationError, ValueError, TypeError, OverflowError):
                pass  # Invalid/deleted targets fall back to the authenticated actor.
        request._habitus_viewed_user = user
    return request._habitus_viewed_user


def is_view_as(request):
    return get_viewed_user(request).pk != request.user.pk


def preview_requested(request):
    """Also reject writes with an invalid preview ID instead of writing the actor."""
    target = request.GET.get('view_as')
    return bool(request.user.is_authenticated and request.user.is_superuser and
                target and target != str(request.user.pk))


def preview_read_only(view):
    """Use on mutation endpoints, including legacy actions accepting GET."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if preview_requested(request):
            return JsonResponse({'error': 'Просмотр пользователя доступен только для чтения.'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def view_as_context(request):
    viewed = get_viewed_user(request)
    preview = is_view_as(request)
    context = {'viewed_user': viewed, 'is_view_as': preview,
               'view_as_query': f'?view_as={viewed.pk}' if preview else ''}
    if request.user.is_superuser:
        model = get_user_model()
        context['view_as_users'] = model.objects.order_by(
            F('last_login').desc(nulls_last=True), model.USERNAME_FIELD, 'pk',
        ).values_list('pk', model.USERNAME_FIELD)
        context['viewed_username'] = viewed.get_username()
    return context
