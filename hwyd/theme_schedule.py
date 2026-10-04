"""Daily theme selection, shared by page rendering and the JSON endpoints."""
from datetime import datetime, time, timedelta, timezone as utc_timezone

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.db.models import F
from django.utils import timezone

from .models import ScheduledTheme, UserActivityLog
from .preferences import THEME_COLOR_FIELDS, THEME_COLOR_DEFAULTS, validate_theme_color
from .timezones import browser_timezone

MANUAL_THEME_KEY = 'habitus_manual_theme_until'
DISPLAY_THEME_KEY = 'habitus_display_theme'
DISPLAY_COLORS_KEY = 'habitus_display_colors'


def default_themes(user):
    """The same defaults can be displayed without inserting rows in a preview."""
    return [ScheduledTheme(user=user, name=name, activation_time=activation, **colors)
            for name, activation, colors in (
                ('Светлая', time(8), THEME_COLOR_DEFAULTS),
                ('Тёмная', time(20), dict(zip(THEME_COLOR_FIELDS, (
                    '#3d4b63', '#18202b', '#594052', '#293649', '#f1f5f9',
                )))),
            )]


def preview_themes(user):
    themes = list(ScheduledTheme.objects.filter(user=user))
    if not themes:
        themes = default_themes(user)
        for index, theme in enumerate(themes, 1):
            theme.pk = -index  # Stable IDs for read-only, unsaved defaults.
    return themes


def presentation_session(request, user=None):
    if user is None or user.pk == request.user.pk:
        return request.session
    # Browser-only manual overrides of another session are not impersonated.
    tz = UserActivityLog.objects.filter(user=user).order_by('-last_visit', '-pk').values_list(
        'timezone', flat=True).first()
    return {'user_timezone': tz}


def ensure_default_themes(user):
    """Bootstrap only an empty owner scope, sharing the CRUD/import writer lock."""
    with transaction.atomic():
        lock_theme_owner(user.pk)
        if ScheduledTheme.objects.filter(user=user).exists():
            return
        for theme in default_themes(user):
            theme.full_clean()
            theme.save()


def lock_theme_owner(user_id, using='default'):
    """Call inside atomic(); get a writer lock before reads on SQLite."""
    model = get_user_model()
    if connections[using].vendor == 'sqlite':
        pk_field = model._meta.pk.attname
        model.objects.using(using).filter(pk=user_id).update(**{pk_field: F(pk_field)})
    else:
        model.objects.using(using).select_for_update().get(pk=user_id)


def theme_colors(instance, strict=False):
    colors = {}
    for field in THEME_COLOR_FIELDS:
        value = getattr(instance, field)
        try:
            validate_theme_color(value)
        except ValidationError:
            if strict:
                raise ValidationError('Сначала сохраните корректные цвета текущей темы (#RRGGBB).')
            value = THEME_COLOR_DEFAULTS[field]
        colors[field] = value
    return colors


def _events(themes, now, user_timezone, offsets):
    local_day = now.astimezone(user_timezone).date()
    for offset in offsets:
        for theme in themes:
            if not theme.is_enabled:
                continue
            event = datetime.combine(local_day + timedelta(days=offset), theme.activation_time, user_timezone)
            # Missing spring-forward times shift forward; a repeated time runs once (fold=0).
            event = event.astimezone(utc_timezone.utc).astimezone(user_timezone)
            yield theme, event.astimezone(utc_timezone.utc)


def current_theme(themes, now, user_timezone):
    """The latest daily local-time event, including yesterday and DST transitions."""
    if user_timezone is None:
        return None
    due = [(theme, event) for theme, event in _events(themes, now, user_timezone, (-2, -1, 0))
           if event <= now.astimezone(utc_timezone.utc)]
    return max(due, key=lambda item: (item[1], item[0].pk))[0] if due else None


def next_activation(themes, now, user_timezone):
    if user_timezone is None:
        return None
    candidates = [event for _, event in _events(themes, now, user_timezone, (0, 1, 2))
                  if event > now.astimezone(utc_timezone.utc)]
    return min(candidates) if candidates else None


def remember_manual_theme(request, theme):
    themes = list(ScheduledTheme.objects.filter(user=request.user, is_enabled=True))
    tz = browser_timezone(request.session.get('user_timezone'))
    event = next_activation(themes, timezone.now(), tz)
    if event:
        request.session[MANUAL_THEME_KEY] = {'theme_id': theme.pk, 'expires_at': event.timestamp()}
    else:
        request.session.pop(MANUAL_THEME_KEY, None)


def resolve_theme(request, themes, now=None, force=False, session=None):
    """Resolve scheduled/manual colors; retain a surviving theme if scheduling is unavailable."""
    now = now or timezone.now()
    session = request.session if session is None else session
    tz = browser_timezone(session.get('user_timezone'))
    active = current_theme(themes, now, tz)
    event = next_activation(themes, now, tz)
    override = session.get(MANUAL_THEME_KEY, {})
    manual_theme = next((theme for theme in themes if theme.pk == override.get('theme_id')), None)
    manual = bool(manual_theme and override.get('expires_at', 0) > now.timestamp())
    if force or (override and not manual):
        session.pop(MANUAL_THEME_KEY, None)
        manual = False
    fallback = next((theme for theme in themes if theme.pk == session.get(DISPLAY_THEME_KEY)), None)
    fallback = fallback or next((theme for theme in themes if theme.is_enabled), None)
    fallback = fallback or (themes[0] if themes else None)
    return (manual_theme if manual else active or fallback), active, manual, tz, event


def display_theme(request, themes=None):
    themes = list(ScheduledTheme.objects.filter(user=request.user)) if themes is None else themes
    return resolve_theme(request, themes)[0]


def schedule_state(request, now=None, apply=False, force=False, themes=None, user=None):
    now = now or timezone.now()
    user = request.user if user is None else user
    preview = user.pk != request.user.pk
    if themes is None:
        themes = preview_themes(user) if preview else list(ScheduledTheme.objects.filter(user=user))
    session = presentation_session(request, user)
    theme, active, manual, tz, event = resolve_theme(request, themes, now, force, session=session)
    colors = theme_colors(theme) if theme else None
    changed = bool(apply and not preview and colors and request.session.get(DISPLAY_COLORS_KEY) != colors)
    if apply and not preview and theme:
        request.session[DISPLAY_THEME_KEY] = theme.pk
        request.session[DISPLAY_COLORS_KEY] = colors
    return {
        'success': True,
        'themes': [{'id': theme.pk, 'name': theme.name, 'activation_time': theme.activation_time.strftime('%H:%M'),
                    'is_enabled': theme.is_enabled, 'colors': theme_colors(theme)} for theme in themes],
        'active_id': active.pk if active and not manual else None,
        'manual_override': manual,
        'timezone': str(tz) if tz else None,
        'server_now': now.isoformat(),
        'next_change_at': event.isoformat() if event else None,
        'colors': colors,
        'changed': changed,
    }
