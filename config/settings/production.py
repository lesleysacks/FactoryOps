"""
FactoryOps — production settings for the factory PC.

DJANGO_SETTINGS_MODULE=config.settings.production

DEBUG is always off here, even if .env still says DEBUG=True.
Required values come from the environment. A missing or placeholder
secret, an empty host list, or a wildcard host prevents startup.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import BASE_DIR, MIDDLEWARE
from .production_checks import validate_production_config


def _flag(name, default='False'):
    return os.getenv(name, default).strip().lower() in {'1', 'true', 'yes', 'on'}


def _csv(name):
    return [item.strip() for item in os.getenv(name, '').split(',') if item.strip()]


DEBUG = False

SECRET_KEY = os.environ.get('SECRET_KEY', '')
ALLOWED_HOSTS = _csv('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = _csv('CSRF_TRUSTED_ORIGINS')
FACTORYOPS_USE_HTTPS = _flag('FACTORYOPS_USE_HTTPS', 'False')

validate_production_config(
    secret_key=SECRET_KEY,
    allowed_hosts=ALLOWED_HOSTS,
    csrf_trusted_origins=CSRF_TRUSTED_ORIGINS,
    debug=DEBUG,
    use_https=FACTORYOPS_USE_HTTPS,
)

_db_path = os.getenv('FACTORYOPS_DB_PATH', '').strip()
if _db_path:
    DATABASES['default']['NAME'] = Path(_db_path)

_media_root = os.getenv('FACTORYOPS_MEDIA_ROOT', '').strip()
if _media_root:
    MEDIA_ROOT = Path(_media_root)
else:
    MEDIA_ROOT = BASE_DIR / 'media'

_log_dir = Path(os.getenv('FACTORYOPS_LOG_DIR', '').strip() or (BASE_DIR / 'logs'))
try:
    _log_dir.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    raise ImproperlyConfigured(
        f'Cannot create the FactoryOps log directory ({_log_dir}).'
    ) from exc

LOG_DIR = _log_dir

if 'whitenoise.middleware.WhiteNoiseMiddleware' not in MIDDLEWARE:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'

if FACTORYOPS_USE_HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
# No SECURE_SSL_REDIRECT here. Turning that on before a TLS proxy is
# listening would make every factory browser fail closed.

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'factoryops.log'),
            'maxBytes': 5_000_000,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'INFO',
    },
    'loggers': {
        'django.request': {
            'handlers': ['file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}


from django.db.backends.signals import connection_created  # noqa: E402


def _configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA busy_timeout=5000;')
        cursor.execute('PRAGMA foreign_keys=ON;')


connection_created.connect(_configure_sqlite)
