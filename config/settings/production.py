"""
FactoryOps production settings.

Select with DJANGO_SETTINGS_MODULE=config.settings.production.
manage.py keeps the development module as its default, so day-to-day
development commands do not pick up this file unless you set the variable.

The database stays SQLite unless FACTORYOPS_SQLITE_PATH points at a different
file. This module does not switch the engine to PostgreSQL and does not run
migrations.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created

from .base import *  # noqa: F401, F403
from .log_setup import build_logging
from .validation import parse_csv, validate_production_config

_https = os.getenv('FACTORYOPS_HTTPS', 'False') == 'True'
_csrf_origins = parse_csv(os.getenv('CSRF_TRUSTED_ORIGINS', ''))

validate_production_config(
    secret_key=SECRET_KEY,
    debug=DEBUG,
    allowed_hosts=ALLOWED_HOSTS,
    csrf_trusted_origins=_csrf_origins,
    https=_https,
)

CSRF_TRUSTED_ORIGINS = _csrf_origins

_sqlite_path = os.getenv('FACTORYOPS_SQLITE_PATH', '').strip()
if _sqlite_path:
    DATABASES['default']['NAME'] = str(Path(_sqlite_path))

_media_root = os.getenv('FACTORYOPS_MEDIA_ROOT', '').strip()
if _media_root:
    MEDIA_ROOT = Path(_media_root)

_static_root = os.getenv('FACTORYOPS_STATIC_ROOT', '').strip()
if _static_root:
    STATIC_ROOT = Path(_static_root)

_log_dir = Path(os.getenv('FACTORYOPS_LOG_DIR', str(BASE_DIR / 'logs')))
try:
    LOGGING = build_logging(_log_dir)
except OSError as exc:
    raise ImproperlyConfigured(
        f'Cannot create the FactoryOps log directory {_log_dir}. '
        f'Check FACTORYOPS_LOG_DIR and the directory permissions. ({exc})'
    ) from exc

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *[
        item
        for item in MIDDLEWARE
        if item != 'django.middleware.security.SecurityMiddleware'
    ],
]

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}
WHITENOISE_USE_FINDERS = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'

if _https:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    # Isolated factory LAN over HTTP. Do not advertise HSTS for plain HTTP.
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False


def _sqlite_pragmas(sender, connection, **kwargs):
    """WAL lets the backup API read a consistent snapshot while the app writes."""
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA busy_timeout=5000;')


connection_created.connect(_sqlite_pragmas)
