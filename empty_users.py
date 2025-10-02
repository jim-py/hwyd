import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_site.settings')
django.setup()

from hwyd.models import Activities
from django.contrib.auth.models import User
from django.db.models import Count, F

# Фильтруем пользователей, отсеивая тех, у кого есть активности
users_without_activities = User.objects.annotate(
    activities_count=Count('activities')
).filter(
    activities_count=0,
).values(
    'username', 'last_login'
).order_by(
    'last_login'
)

for user in users_without_activities:
    print(f"Пользователь: {user['username']}, дата последнего входа: {user['last_login']}")
