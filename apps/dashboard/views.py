"""
FactoryOps Dashboard — Role-oriented operational views.

Dashboards read existing materials, production, warehouse, and order records.
They do not write inventory, production, or order history.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from . import services
from .helpers import crumbs
from .permissions import (
    EXECUTIVE_ROLES,
    INVENTORY_ROLES,
    MANAGER_ROLES,
    OPERATOR_ROLES,
    SUPERVISOR_ROLES,
    can_record_production,
    home_dashboard_name,
    role_required,
)
from .querysets import active_lines_for, active_machines_for, user_factory


def _tone(value, *, danger=False, info=False):
    if value:
        if danger:
            return 'danger'
        if info:
            return 'info'
        return 'warning'
    return 'success'


@login_required
def home(request):
    return redirect(home_dashboard_name(request.user))


@role_required(*OPERATOR_ROLES)
def operator(request):
    metrics = services.operator_dashboard(request.user)
    return render(request, 'dashboard/operator.html', {
        'metrics': metrics,
        'page_title': 'Operator dashboard',
        'page_subtitle': "Today's operations",
        'breadcrumbs': crumbs({'label': 'Operations'}),
        'factory': user_factory(request.user),
        'lines': list(active_lines_for(request.user)),
        'machines': list(active_machines_for(request.user)),
        'can_record_production': can_record_production(request.user),
    })


@role_required(*SUPERVISOR_ROLES)
def supervisor(request):
    metrics = services.supervisor_dashboard(request.user)
    return render(request, 'dashboard/supervisor.html', {
        'metrics': metrics,
        'page_title': 'Supervisor dashboard',
        'page_subtitle': 'Production oversight',
        'breadcrumbs': crumbs({'label': 'Production'}),
        'active_tone': _tone(metrics['active_run_count'], info=True),
        'waste_tone': _tone(metrics['waste_today'], danger=True),
        'reject_tone': _tone(metrics['rejects_today'], danger=True),
        'variance_tone': _tone(metrics['variance_count'], danger=True),
    })


@role_required(*MANAGER_ROLES)
def manager(request):
    metrics = services.manager_dashboard(request.user)
    return render(request, 'dashboard/manager.html', {
        'metrics': metrics,
        'page_title': 'Factory manager dashboard',
        'page_subtitle': 'Production, inventory, and fulfilment',
        'breadcrumbs': crumbs({'label': 'Orders'}),
    })


@role_required(*EXECUTIVE_ROLES)
def executive(request):
    metrics = services.executive_dashboard(request.user)
    return render(request, 'dashboard/executive.html', {
        'metrics': metrics,
        'page_title': 'Executive dashboard',
        'page_subtitle': 'Top operational KPIs',
        'breadcrumbs': crumbs({'label': 'Reports'}),
    })


@role_required(*INVENTORY_ROLES)
def inventory(request):
    metrics = services.inventory_dashboard(request.user)
    return render(request, 'dashboard/inventory.html', {
        'metrics': metrics,
        'page_title': 'Inventory dashboard',
        'page_subtitle': 'Stock snapshots and exceptions',
        'breadcrumbs': crumbs({'label': 'Inventory'}),
    })
