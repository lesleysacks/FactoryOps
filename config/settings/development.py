"""
FactoryOps — Development Settings
Extends base.py. Used when DJANGO_SETTINGS_MODULE=config.settings.development
(set by manage.py by default).
"""

from .base import *  # noqa: F401, F403

# Development overrides — base.py loads DEBUG and ALLOWED_HOSTS from .env
# No overrides needed here currently; this file exists for future
# development-specific configuration (e.g. debug toolbar, query logging).
