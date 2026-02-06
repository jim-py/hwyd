# my_site/celery.py
from settings import hosting
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_site.settings')

app = Celery('my_site')

if hosting:
    app.conf.broker_url = 'redis+socket:///home/a0853298/tmp/redis.sock'
    app.conf.result_backend = 'redis+socket:///home/a0853298/tmp/redis.sock'

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
app.conf.beat_scheduler = 'django_celery_beat.schedulers.DatabaseScheduler'
