"""Management status for Google Sheets reporting."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.models import Role
from apps.reports.sync import run_sync, status_snapshot


def can_manage_sheet_sync(user):
    """Administrators only. Operators, QC, and supervisors cannot push reports."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) == Role.ADMIN


@login_required
@require_http_methods(['GET', 'POST'])
def sheets_status(request):
    if not can_manage_sheet_sync(request.user):
        raise PermissionDenied('You do not have access to sheet sync.')
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action not in ('sync', 'retry'):
            messages.error(request, 'Unknown sheet sync action.')
            return redirect('reports:sheets_status')
        result = run_sync(
            factory_id=request.user.factory_id,
            trigger='manual',
            actor_id=request.user.pk,
            ignore_backoff=(action == 'retry'),
        )
        if result.outcome in ('ok', 'disabled'):
            messages.success(request, result.message)
        elif result.outcome in ('failed', 'partial', 'misconfigured'):
            messages.error(request, result.message)
        else:
            messages.warning(request, result.message)
        return redirect('reports:sheets_status')
    return render(request, 'reports/sheets_status.html', {
        'snapshot': status_snapshot(request.user.factory_id),
        'page_title': 'Sheet sync',
        'page_subtitle': 'Google Sheets reporting',
        'breadcrumbs': [
            {'label': 'Orders', 'url': '/manager/'},
            {'label': 'Sheet sync'},
        ],
    })
