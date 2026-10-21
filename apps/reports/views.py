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
"""
FactoryOps reports — read-only management views.

Dates are UTC calendar days. These views do not write production or QC rows.
"""

from django.core.exceptions import ValidationError
from django.shortcuts import render

from apps.accounts.access import _platform_admin
from apps.dashboard.helpers import crumbs
from apps.dashboard.permissions import SUPERVISOR_ROLES, role_required
from apps.reports.services import production_summary, qc_variance_report
from apps.reports.windows import resolve_window, utc_today, window_for_week_ending


def _validation_text(exc):
    return ' '.join(str(message) for message in exc.messages)


def _scope_notice(user):
    if _platform_admin(user):
        return 'All factories. Dates are UTC calendar days.'
    factory = getattr(user, 'factory', None)
    if factory is not None:
        return f'{factory.name}. Dates are UTC calendar days.'
    return (
        'This account is not assigned to a factory, so the report is empty. '
        'Dates are UTC calendar days.'
    )


def _is_rolling_seven_day(window):
    """True only for the seven UTC days that end today."""
    if window is None:
        return False
    rolling = window_for_week_ending(utc_today())
    return window.start == rolling.start and window.end == rolling.end


def _summary_title(window):
    if window.day_count == 1:
        return 'Daily production summary'
    if _is_rolling_seven_day(window):
        return 'Rolling seven-day production summary'
    return 'Production summary'


def _load_window(request):
    preset = request.GET.get('preset') or 'day'
    if preset not in ('day', 'week'):
        preset = 'day'
    try:
        window = resolve_window(
            request.GET.get('start'),
            request.GET.get('end'),
            preset=preset,
        )
    except ValidationError as exc:
        return None, preset, _validation_text(exc)
    return window, preset, ''


def _filter_values(request, window):
    start_value = (request.GET.get('start') or '').strip()
    end_value = (request.GET.get('end') or '').strip()
    if window is not None and not start_value and not end_value:
        start_value = window.start.isoformat()
        end_value = window.end.isoformat()
    return start_value, end_value


@role_required(*SUPERVISOR_ROLES)
def production_summary_view(request):
    window, preset, error = _load_window(request)
    start_value, end_value = _filter_values(request, window)
    summary = production_summary(request.user, window) if window else None
    title = _summary_title(window) if window else 'Production summary'
    return render(request, 'reports/production.html', {
        'page_title': title,
        'page_subtitle': _scope_notice(request.user),
        'breadcrumbs': crumbs({'label': 'Output reports'}),
        'summary': summary,
        'window': window,
        'preset': preset,
        'error': error,
        'start_value': start_value,
        'end_value': end_value,
        'rolling_seven_day': _is_rolling_seven_day(window),
    })


@role_required(*SUPERVISOR_ROLES)
def qc_variance_view(request):
    window, preset, error = _load_window(request)
    start_value, end_value = _filter_values(request, window)
    report = qc_variance_report(request.user, window) if window else None
    return render(request, 'reports/qc_variance.html', {
        'page_title': 'QC variance',
        'page_subtitle': _scope_notice(request.user),
        'breadcrumbs': crumbs({'label': 'QC variance'}),
        'report': report,
        'window': window,
        'preset': preset,
        'error': error,
        'start_value': start_value,
        'end_value': end_value,
        'rolling_seven_day': _is_rolling_seven_day(window),
    })
