"""
FactoryOps Dashboard — Role access helpers.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.accounts.models import Role


OPERATOR_ROLES = (Role.OPERATOR, Role.QC, Role.SUPERVISOR, Role.ADMIN)
PRODUCTION_ROLES = (Role.OPERATOR, Role.SUPERVISOR, Role.ADMIN)
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
    return getattr(user, 'role', None) in PRODUCTION_ROLES


def home_dashboard_name(user):
    if user.role == Role.ADMIN:
        return 'dashboard:manager'
    if user.role == Role.SUPERVISOR:
        return 'dashboard:supervisor'
    return 'dashboard:operator'
