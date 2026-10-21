"""
FactoryOps Audit — the only write path for audit history and controlled corrections.
"""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEvent

CORRECTION_FIELDS = {
    'qcverification': {'qc_verified_quantity', 'recorded_quantity'},
    'productionoutput': {'quantity'},
    'productionrun': {'planned_pack_quantity'},
}


def _text(value):
    if value is None:
        return ''
    return str(value)


def _factory_of(instance):
    if getattr(instance, 'factory_id', None):
        return instance.factory
    run = getattr(instance, 'production_run', None)
    if run is not None:
        return run.factory
    raise ValidationError('Cannot determine the factory for this record.')


def record_event(
    *,
    factory,
    actor,
    action,
    target,
    field_name='',
    old_value='',
    new_value='',
    reason='',
):
    if target is None or not getattr(target, 'pk', None):
        raise ValidationError('Audit events require a saved target record.')
    content_type = ContentType.objects.get_for_model(target)
    return AuditEvent.objects.create(
        factory=factory,
        actor=actor,
        action=action,
        target_content_type=content_type,
        target_object_id=target.pk,
        field_name=field_name or '',
        old_value=_text(old_value),
        new_value=_text(new_value),
        reason=reason or '',
    )


def apply_controlled_correction(instance, field, new_value, *, actor, reason):
    """Change one field and keep the previous value in an audit event.

    The operator's original production rows stay in place unless that row is
    the instance being corrected. A correction of QC recorded quantity does
    not rewrite ProductionOutput.
    """
    if actor is None or getattr(actor, 'role', None) not in (Role.SUPERVISOR, Role.ADMIN):
        raise ValidationError('Only a supervisor or admin can correct a record.')
    if not (reason or '').strip():
        raise ValidationError({'reason': 'A reason is required.'})
    allowed = CORRECTION_FIELDS.get(instance._meta.model_name, set())
    if field not in allowed:
        raise ValidationError({'field_name': 'This field cannot be corrected here.'})
    old_value = getattr(instance, field)
    if old_value == new_value:
        raise ValidationError({field: 'The new value matches the current value.'})
    factory = _factory_of(instance)
    with transaction.atomic():
        setattr(instance, field, new_value)
        instance.save()
        record_event(
            factory=factory,
            actor=actor,
            action=AuditAction.CORRECTION,
            target=instance,
            field_name=field,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
        )
    return instance
