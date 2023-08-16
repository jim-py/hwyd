import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')
django.setup()

from hwyd.models import *

ACTIVITIES_NAMES = ['Пил воду', 'Записывал еду', 'Не дрочил', 'Чистил зубы (утро)', 'Чистил зубы (день)',
                    'Чистил зубы (вечер)', 'Медитировал (утро)', 'Медитировал (день)', 'Медитировал (вечер)',
                    'Размялся', 'Висел вниз головой', 'Принял душ', 'Гулял', 'Бегал', 'Лёг спать около 22:00',
                    'Подвёл итоги дня', 'Читал книгу', 'Проходил курс 1С', 'Прибирался']

for name in ACTIVITIES_NAMES:
    activity = Activities.objects.create(name=name, color='#ffffff', backgroundColor='#000000')
