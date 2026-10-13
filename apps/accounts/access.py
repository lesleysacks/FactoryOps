"""
FactoryOps account access.

Role is who the person is (operator, QC, supervisor, admin).
Responsibility groups are what an operator is trusted to do.
Views must not compare usernames.
"""

from django.contrib.auth.models import Group
from django.core.exceptions import FieldDoesNotExist, PermissionDenied, ValidationError

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


def _admin_staff_gate(user, allowed):
    """Superuser bypasses. Everyone else needs the staff flag and the floor rule."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if not getattr(user, 'is_staff', False):
        return False
    return bool(allowed)


def production_admin_allowed(user):
    """Django admin is an alternate production-run screen and uses the same rule."""
    return _admin_staff_gate(user, can_manage_production(user))


def inventory_admin_allowed(user):
    """Stock receipts, counts, consumption, and reconciliation in Django admin."""
    return _admin_staff_gate(user, can_record_inventory(user))


def qc_admin_allowed(user):
    """QC admin is read-only inspection. The same roles can open the QC queue."""
    from apps.dashboard.permissions import can_perform_qc

    return _admin_staff_gate(user, can_perform_qc(user))


def configuration_admin_allowed(user):
    """Users, groups, factories, machines, catalogue, and master data."""
    return _admin_staff_gate(user, getattr(user, 'role', None) == Role.ADMIN)


def audit_admin_allowed(user):
    """Supervisors and admins may read the audit log. Nobody writes it here."""
    return _admin_staff_gate(
        user,
        getattr(user, 'role', None) in (Role.SUPERVISOR, Role.ADMIN),
    )


def _platform_admin(user):
    """A platform admin has no factory. A plant admin stays inside one factory."""
    if getattr(user, 'factory_id', None):
        return False
    return bool(
        getattr(user, 'is_superuser', False)
        or getattr(user, 'role', None) == Role.ADMIN
    )


def scope_factory_admin(queryset, user, lookup):
    if not lookup:
        return queryset
    if _platform_admin(user):
        return queryset
    factory_id = getattr(user, 'factory_id', None)
    if factory_id:
        return queryset.filter(**{lookup: factory_id})
    return queryset.none()


def scope_production_admin(queryset, user, prefix=''):
    factory_lookup = f'{prefix}factory_id' if prefix else 'factory_id'
    machine_lookup = f'{prefix}machine__in' if prefix else 'machine__in'
    if _platform_admin(user):
        scoped = queryset
    elif getattr(user, 'factory_id', None):
        scoped = queryset.filter(**{factory_lookup: user.factory_id})
    else:
        scoped = queryset.none()
    if machines_limited_to_assignment(user):
        scoped = scoped.filter(**{machine_lookup: user.assigned_machines.all()})
    return scoped


def _field_exists(obj, name):
    try:
        obj._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


def _related_factory_id(obj, field_name):
    if not _field_exists(obj, field_name):
        return None
    related = getattr(obj, field_name, None)
    if related is None:
        return None
    if field_name == 'variant':
        return related.product.factory_id
    if field_name == 'batch':
        return related.material.factory_id
    if field_name == 'machine':
        return related.production_line.factory_id
    if field_name == 'qc_verification':
        return related.production_run.factory_id
    if field_name == 'order_line':
        return related.customer_order.factory_id
    if field_name == 'dispatch':
        return related.warehouse.factory_id
    if field_name == 'customer_order':
        return related.factory_id
    if field_name == 'production_run':
        return related.factory_id
    if field_name == 'production_line':
        return related.factory_id
    return getattr(related, 'factory_id', None)


def enforce_admin_factory(user, obj):
    """Keep a plant user's admin save inside that factory.

    A platform admin (no factory) is not rewritten. Model validation still
    rejects mismatched factory links on the record itself.
    """
    if _platform_admin(user):
        return
    factory_id = getattr(user, 'factory_id', None)
    if not factory_id:
        raise PermissionDenied('Your account is not assigned to a factory.')
    if _field_exists(obj, 'factory'):
        obj.factory_id = factory_id
    for field_name in (
        'material',
        'warehouse',
        'finished_good',
        'product',
        'packaging',
        'category',
        'customer',
        'variant',
        'batch',
        'machine',
        'production_line',
        'production_run',
        'qc_verification',
        'customer_order',
        'order_line',
        'dispatch',
    ):
        related_factory_id = _related_factory_id(obj, field_name)
        if related_factory_id not in (None, factory_id):
            raise PermissionDenied('That record is not in your factory.')


def enforce_production_admin_write(user, obj):
    """Production admin saves use the factory boundary and assigned machines."""
    enforce_admin_factory(user, obj)
    if not machines_limited_to_assignment(user):
        return
    machine = getattr(obj, 'machine', None) if _field_exists(obj, 'machine') else None
    if machine is None and _field_exists(obj, 'production_run'):
        run = getattr(obj, 'production_run', None)
        machine = getattr(run, 'machine', None) if run is not None else None
    machine_id = getattr(machine, 'pk', None)
    if machine_id is None or not user.assigned_machines.filter(pk=machine_id).exists():
        raise PermissionDenied('This machine is not assigned to you.')


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
