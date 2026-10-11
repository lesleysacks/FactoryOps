"""
FactoryOps Dashboard — Role access helpers.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.accounts.access import can_manage_production, can_record_inventory
from apps.accounts.models import Role


OPERATOR_ROLES = (Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN)
PRODUCTION_ROLES = (Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN)
QC_ROLES = (Role.QC, Role.SUPERVISOR, Role.ADMIN)
SUPERVISOR_ROLES = (Role.SUPERVISOR, Role.ADMIN)
MANAGER_ROLES = (Role.ADMIN,)
EXECUTIVE_ROLES = (Role.ADMIN,)
INVENTORY_ROLES = (Role.SUPERVISOR, Role.ADMIN)


def role_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied('You do not have access to this dashboard.')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def can_record_production(user):
    return can_manage_production(user)


def can_perform_qc(user):
    return getattr(user, 'role', None) in QC_ROLES


def access_required(check):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied('You do not have access to this screen.')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


production_required = access_required(can_manage_production)
inventory_required = access_required(can_record_inventory)


def home_dashboard_name(user):
    if user.role == Role.ADMIN:
        return 'dashboard:manager'
    if user.role == Role.SUPERVISOR:
        return 'dashboard:supervisor'
    if user.role == Role.QC:
        return 'dashboard:qc_queue'
    return 'dashboard:operator'
