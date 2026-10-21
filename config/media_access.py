"""Serve uploaded files only to an authenticated, factory-scoped user."""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from apps.accounts.models import Role


QC_PHOTO_ROLES = (Role.QC, Role.SUPERVISOR, Role.ADMIN)


def _is_platform_admin(user):
    """An ADMIN or superuser with no factory can read every plant's files."""
    if getattr(user, 'factory_id', None):
        return False
    return bool(
        getattr(user, 'is_superuser', False)
        or getattr(user, 'role', None) == Role.ADMIN
    )


def _can_read_qc_photo(user):
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) in QC_PHOTO_ROLES


def user_can_read_media(user, relative_path):
    """QC photos are qc/<factory id>/... and are not for operators.

    A factory-bound user can read a QC photo only for that factory.
    An ADMIN or superuser with no factory can read every plant's QC photos.
    Other files stay limited to that unassigned platform admin.
    """
    parts = Path(relative_path).parts
    if len(parts) >= 2 and parts[0] == 'qc':
        if not _can_read_qc_photo(user):
            return False
        if getattr(user, 'factory_id', None) is not None:
            return str(user.factory_id) == parts[1]
        return _is_platform_admin(user)
    return _is_platform_admin(user)


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
