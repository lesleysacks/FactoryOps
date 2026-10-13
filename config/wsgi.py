"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Production is the default for the WSGI entry point. manage.py still
# selects development before Django starts, so runserver is unchanged.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')


application = get_wsgi_application()
