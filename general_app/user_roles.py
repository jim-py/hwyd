def display_role(user):
    """Public name decoration; superusers take precedence over staff."""
    if user.is_superuser:
        return 'owner'
    if user.is_staff:
        return 'admin'
    return ''
