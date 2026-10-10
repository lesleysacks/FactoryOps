"""Serve uploaded files only to an authenticated, factory-scoped user."""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from apps.accounts.models import Role


def user_can_read_media(user, relative_path):
    """QC photos are stored as qc/<factory id>/... . Other files stay admin-only."""
    parts = Path(relative_path).parts
    if len(parts) >= 2 and parts[0] == 'qc':
        if user.factory_id is not None:
            return str(user.factory_id) == parts[1]
        return bool(user.is_superuser or getattr(user, 'role', None) == Role.ADMIN)
    return bool(
        user.factory_id is None
        and (user.is_superuser or getattr(user, 'role', None) == Role.ADMIN)
    )


def resolve_media_file(relative_path):
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise Http404
    if not target.is_file():
        raise Http404
    return target


@login_required
@require_GET
def protected_media(request, relative_path):
    if not user_can_read_media(request.user, relative_path):
        raise PermissionDenied('You cannot open this file.')
    target = resolve_media_file(relative_path)
    content_type = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
    return FileResponse(target.open('rb'), content_type=content_type)
