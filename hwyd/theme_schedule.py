"""Daily theme selection, shared by page rendering and the JSON endpoints."""
from datetime import datetime, timedelta, timezone as utc_timezone

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import connections
from django.db.models import F
from django.utils import timezone

from .models import ScheduledTheme, Settings
from .preferences import THEME_COLOR_FIELDS, THEME_COLOR_DEFAULTS, validate_theme_color
from .timezones import browser_timezone

MANUAL_THEME_KEY = 'habitus_manual_theme_until'


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


def selected_settings(user):
    return Settings.objects.filter(user=user, selected=True).order_by('pk').first()


def remember_manual_theme(request, preset):
    themes = list(ScheduledTheme.objects.filter(user=request.user, is_enabled=True))
    tz = browser_timezone(request.session.get('user_timezone'))
    event = next_activation(themes, timezone.now(), tz)
    if event:
        request.session[MANUAL_THEME_KEY] = {'preset_id': preset.pk, 'expires_at': event.timestamp()}
    else:
        request.session.pop(MANUAL_THEME_KEY, None)


def schedule_state(request, preset=None, now=None, apply=False, force=False, themes=None):
    now = now or timezone.now()
    tz = browser_timezone(request.session.get('user_timezone'))
    themes = list(ScheduledTheme.objects.filter(user=request.user)) if themes is None else themes
    preset = preset if preset is not None else selected_settings(request.user)
    active = current_theme(themes, now, tz)
    event = next_activation(themes, now, tz)
    override = request.session.get(MANUAL_THEME_KEY, {})
    manual = bool(preset and override.get('preset_id') == preset.pk and override.get('expires_at', 0) > now.timestamp())
    if force or (override and not manual):
        request.session.pop(MANUAL_THEME_KEY, None)
        manual = False
    changed = False
    if apply and preset and active and not manual:
        colors = theme_colors(active, strict=True)
        changed = any(getattr(preset, field) != value for field, value in colors.items())
        if changed:
            Settings.objects.filter(pk=preset.pk, user=request.user, selected=True).update(**colors)
            for field, value in colors.items():
                setattr(preset, field, value)
    return {
        'success': True,
        'themes': [{'id': theme.pk, 'name': theme.name, 'activation_time': theme.activation_time.strftime('%H:%M'),
                    'is_enabled': theme.is_enabled, 'colors': theme_colors(theme)} for theme in themes],
        'active_id': active.pk if active and not manual else None,
        'manual_override': manual,
        'timezone': str(tz) if tz else None,
        'server_now': now.isoformat(),
        'next_change_at': event.isoformat() if event else None,
        'colors': theme_colors(preset) if preset else None,
        'changed': changed,
    }
