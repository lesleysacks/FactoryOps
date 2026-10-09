"""Deployment HTTP endpoints. Domain workflows stay in the apps packages."""

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.db import connection
from django.http import Http404, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.views.static import serve

logger = logging.getLogger('factoryops.health')


def database_ready() -> None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()


@never_cache
@require_GET
def health(request):
    """Readiness probe. No secrets, counts, or exception text in the body."""
    try:
        database_ready()
    except Exception:
        logger.exception('Readiness check failed')
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})


@login_required
@require_GET
def protected_media(request, path):
    """Serve uploaded files to signed-in users when DEBUG is off.

    Development keeps Django's static() helper. Production has no separate
    web server, so this view is the media path. Anonymous callers are sent
    to the existing login page.
    """
    from django.conf import settings

    try:
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    except SuspiciousFileOperation as exc:
        raise Http404('Invalid media path') from exc
