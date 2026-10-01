from .models import Settings
from .preferences import FONT_FAMILIES


def user_typography(request):
    """Use the selected Habitus preset on every ordinary site page."""
    font = 'Montserrat'
    if request.user.is_authenticated:
        preset = getattr(request, 'habitus_settings', None)
        if preset is None:
            preset = Settings.objects.filter(user=request.user, selected=True).order_by('pk').first()
        font = preset.fontFamily if preset else 'Inter'
        # Only existing font options can become CSS, including legacy saved values.
        if font not in FONT_FAMILIES:
            font = 'Inter'
    return {'app_font_family': font}
