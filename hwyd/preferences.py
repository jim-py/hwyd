"""Shared names for the existing server-side display preferences."""
from django.core.validators import RegexValidator

THEME_COLOR_FIELDS = (
    'rowColumnLight', 'backgroundColor', 'tableHeadColorWeekend',
    'tableHeadColor', 'tableHeadTextColor',
)
THEME_COLOR_DEFAULTS = dict(zip(THEME_COLOR_FIELDS, (
    '#e7e7e7', '#f0f0f0', '#eeb3b3', '#e6e4ce', '#000000',
)))
validate_theme_color = RegexValidator(r'\A#[0-9a-fA-F]{6}\Z', 'Цвет должен иметь формат #RRGGBB.')

FONT_FAMILIES = (
    'Consolas', 'Montserrat', 'Montserrat Alternates', 'Georgia',
    'JetBrains Mono', 'Arial', 'Courier New', 'Lucida Console',
    'Trebuchet MS', 'Istok Web', 'Roboto Mono', 'Inter', 'Ubuntu',
    'Comic Sans MS',
)

UI_VISIBILITY_FIELDS = (
    'showStreak', 'showTop', 'showFeedback', 'showCompletedButton', 'showChat',
    'showActivityIcons', 'showViewSwitch', 'showThemeSchedule',
)
