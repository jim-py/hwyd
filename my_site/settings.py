import os
from pathlib import Path
from django.utils.translation import gettext_lazy as _

dir_test = '/home/a0853298/proj_test/myproject/'
dir_proj = '/home/a0853298/proj/myproject/'
test_server = True if 'proj_test' in str(os.path.dirname(os.path.abspath(__file__))) else False

# Технический перерыв
MAINTENANCE_MODE = False

# Блокировка для тестового сайта
BLOCK_ALL_PAGES = test_server

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_URL = '/static/'

# Проверка выполнения кода на сервере хостинга или локально
hosting = str(BASE_DIR).find('Productivum') == -1
if hosting:
    if test_server:
        direction = dir_test
    else:
        direction = dir_proj

    ALLOWED_HOSTS = ['a0853298.xsph.ru', 'productivum.ru']
    STATIC_ROOT = direction + 'static/'
else:
    ALLOWED_HOSTS = ['*']
    STATIC_ROOT = str(BASE_DIR.joinpath('static'))

SECRET_KEY = '2v^46_-9jw*x(weg8j9n-3ad%p0&h^avvfy3c(wj$jnyx)3i!&'

DEBUG = not hosting

LOGOUT_REDIRECT_URL = '/'

INSTALLED_APPS = [
    'whitenoise.runserver_nostatic',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_user_agents',
    'general_app.apps.GeneralAppConfig',
    'hwyd.apps.HwydConfig',
    # 'budget.apps.BudgetConfig',
    'todos.apps.TodosConfig',
    'taggit',
    'pomodoro',
    "debug_toolbar",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'maintenance_middleware.MaintenanceMiddleware',
    'maintenance_middleware.BlockAllPagesWithToggleMiddleware',
]

ROOT_URLCONF = 'my_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'my_site.wsgi.application'

if hosting:
    if test_server:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': 'a0853298_test',
                'USER': 'a0853298_test',
                'PASSWORD': 'kwriCWcr3AQw5PxK2hKN7WUdTTF7gd',
                'HOST': 'localhost',
                'PORT': '3306',
                'OPTIONS': {
                    'charset': 'utf8mb4',
                },
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': 'a0853298_productivum',
                'USER': 'a0853298_productivum',
                'PASSWORD': 'JzwEambciu86h9EoJYfNy7LofL5nAw',
                'HOST': 'localhost',
                'PORT': '3306',
                'OPTIONS': {
                    'charset': 'utf8mb4',
                },
            }
        }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru'

LANGUAGES = [
    ('ru', _('Russian')),
]

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = False

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
