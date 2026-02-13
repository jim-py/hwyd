from pathlib import Path
from django.utils.translation import gettext_lazy as _

# =========================================================
# BASE
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DIR_PROD = '/home/a0853298/proj/myproject/'

HOSTING = 'Productivum' not in str(BASE_DIR)

DEBUG = not HOSTING

SECRET_KEY = '2v^46_-9jw*x(weg8j9n-3ad%p0&h^avvfy3c(wj$jnyx)3i!&'

LOGOUT_REDIRECT_URL = '/'

MAINTENANCE_MODE = False


# =========================================================
# STATIC FILES
# =========================================================

STATIC_URL = '/static/'

if HOSTING:
    ALLOWED_HOSTS = [
        'a0853298.xsph.ru',
        'productivum.ru',
    ]
    STATIC_ROOT = f'{DIR_PROD}static/'
else:
    ALLOWED_HOSTS = ['*']
    STATIC_ROOT = BASE_DIR / 'static'


# =========================================================
# APPLICATIONS
# =========================================================

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'whitenoise.runserver_nostatic',
    'django_user_agents',
    'taggit',
    'pomodoro',
    'debug_toolbar',
    'notifications',
    'widget_tweaks',
    'webpush',
    'django_extensions',
    'django_celery_beat',
]

LOCAL_APPS = [
    'general_app.apps.GeneralAppConfig',
    'hwyd.apps.HwydConfig',
    'todos.apps.TodosConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# =========================================================
# WEB PUSH
# =========================================================

WEBPUSH_SETTINGS = {
    "VAPID_PUBLIC_KEY": "BB83EoTTC8cO73kgpsJqVBlSH1FrivQoHgG5hD33jXLbDAXiLBvb_PLzVbpeEed5keHXcSKPuYVMdoEZuzqSqME",
    "VAPID_PRIVATE_KEY":"DwEU-oa03b66w492jz_KCmWxx3ulDJtVsLYn5_Xh44c",
    "VAPID_ADMIN_EMAIL": "ddimsa70@gmail.com"
}


# =========================================================
# CELERY
# =========================================================

if HOSTING:
    CELERY_BROKER_URL = 'redis+socket:///home/a0853298/tmp/redis.sock'
    CELERY_RESULT_BACKEND = 'redis+socket:///home/a0853298/tmp/redis.sock'
else:
    CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'

CELERY_ENABLE_UTC = True
CELERY_TIMEZONE = 'Europe/Moscow'


# =========================================================
# MIDDLEWARE
# =========================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'django_user_agents.middleware.UserAgentMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'maintenance_middleware.MaintenanceMiddleware',
    'maintenance_middleware.UserActivityLoggingMiddleware',
]


# =========================================================
# TEMPLATES
# =========================================================

ROOT_URLCONF = 'my_site.urls'
WSGI_APPLICATION = 'my_site.wsgi.application'

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
                'notifications.context_processors.unread_notification',
            ],
        },
    },
]


# =========================================================
# DATABASE
# =========================================================

if HOSTING:
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


# =========================================================
# AUTH PASSWORD VALIDATION
# =========================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# =========================================================
# INTERNATIONALIZATION
# =========================================================

LANGUAGE_CODE = 'ru'
LANGUAGES = [
    ('ru', _('Russian')),
]

TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True


# =========================================================
# DJANGO DEFAULTS
# =========================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
