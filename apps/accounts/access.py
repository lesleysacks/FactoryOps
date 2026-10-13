"""
FactoryOps account access.

Role is who the person is (operator, QC, supervisor, admin).
Responsibility groups are what an operator is trusted to do.
Views must not compare usernames.
"""

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from apps.accounts.models import Role


PRINTING_STATION = 'factoryops.printing_station'
INVENTORY = 'factoryops.inventory'

RESPONSIBILITY_LABELS = {
    PRINTING_STATION: 'Head of Printing Station',
    INVENTORY: 'Inventory',
}
RESPONSIBILITY_GROUPS = frozenset(RESPONSIBILITY_LABELS)


def responsibility_codes(user):
    """Operator duty groups only. Other roles are not limited by these groups."""
    if getattr(user, 'role', None) != Role.OPERATOR or not getattr(user, 'pk', None):
        return frozenset()
    return frozenset(
        user.groups.filter(name__in=RESPONSIBILITY_GROUPS).values_list('name', flat=True)
    )


def can_manage_production(user):
    """Start and manage production runs. QC never can. Inventory-only operators cannot."""
    role = getattr(user, 'role', None)
    if role in (Role.SUPERVISOR, Role.ADMIN):
        return True
    if role != Role.OPERATOR:
        return False
    codes = responsibility_codes(user)
    if not codes:
        return True
    return PRINTING_STATION in codes


def can_record_inventory(user):
    """Receipts, stock counts, and consumption. Printing-only operators cannot."""
    role = getattr(user, 'role', None)
    if role in (Role.SUPERVISOR, Role.ADMIN):
        return True
    if role != Role.OPERATOR:
        return False
    codes = responsibility_codes(user)
    if not codes:
        return True
    return INVENTORY in codes


def machines_limited_to_assignment(user):
    return (
        getattr(user, 'role', None) == Role.OPERATOR
        and PRINTING_STATION in responsibility_codes(user)
    )


def production_admin_allowed(user):
    """Django admin is an alternate production-run screen and uses the same rule."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if not getattr(user, 'is_staff', False):
        return False
    return can_manage_production(user)


def scope_production_admin(queryset, user, prefix=''):
    factory_lookup = f'{prefix}factory_id' if prefix else 'factory_id'
    machine_lookup = f'{prefix}machine__in' if prefix else 'machine__in'
    if getattr(user, 'is_superuser', False) and not getattr(user, 'factory_id', None):
        scoped = queryset
    elif getattr(user, 'factory_id', None):
        scoped = queryset.filter(**{factory_lookup: user.factory_id})
    else:
        scoped = queryset.none()
    if machines_limited_to_assignment(user):
        scoped = scoped.filter(**{machine_lookup: user.assigned_machines.all()})
    return scoped


def assert_can_manage_production(user):
    if not can_manage_production(user):
        raise ValidationError('You cannot manage production runs.')


def assert_can_record_inventory(user):
    if not can_record_inventory(user):
        raise ValidationError('You cannot record inventory.')


def assert_machine_assignment(user, machine):
    if not machines_limited_to_assignment(user):
        return
    machine_id = getattr(machine, 'pk', None)
    if machine_id is None or not user.assigned_machines.filter(pk=machine_id).exists():
        raise ValidationError('This machine is not assigned to you.')


def ensure_responsibility_groups():
    groups = {}
    for name in RESPONSIBILITY_GROUPS:
        group, _created = Group.objects.get_or_create(name=name)
        groups[name] = group
    return groups
