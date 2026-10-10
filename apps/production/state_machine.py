"""
FactoryOps Production — server-enforced stage transitions.

Legacy runs (stage is null) are never forced into this machine.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.dashboard.permissions import PRODUCTION_ROLES, QC_ROLES, SUPERVISOR_ROLES
from apps.production.models import (
    ProductionRun,
    ProductionRunStatus,
    ProductionStage,
    QCVerificationStatus,
)
from apps.production.variance import (
    VARIANCE_EXCEPTION,
    VARIANCE_INSUFFICIENT,
    VARIANCE_OK,
    VARIANCE_WITHIN_TOLERANCE,
    expected_individual_units,
    recorded_quantity_for_run,
    variance_for_run,
)
from apps.production.workflow import _require_factory, allocate_reference

RESOLVED_VARIANCE = {VARIANCE_OK, VARIANCE_WITHIN_TOLERANCE}

TRANSITIONS = {
    ProductionStage.DRAFT: {
        ProductionStage.INPUTS_COMPLETE: PRODUCTION_ROLES,
        ProductionStage.CANCELLED: PRODUCTION_ROLES,
    },
    ProductionStage.INPUTS_COMPLETE: {
        ProductionStage.PRODUCTION_ACTIVE: PRODUCTION_ROLES,
        ProductionStage.DRAFT: PRODUCTION_ROLES,
        ProductionStage.CANCELLED: PRODUCTION_ROLES,
    },
    ProductionStage.PRODUCTION_ACTIVE: {
        ProductionStage.OUTPUT_RECORDED: PRODUCTION_ROLES,
        ProductionStage.CANCELLED: PRODUCTION_ROLES,
    },
    ProductionStage.OUTPUT_RECORDED: {
        ProductionStage.QC_REQUIRED: PRODUCTION_ROLES,
        ProductionStage.CANCELLED: PRODUCTION_ROLES,
    },
    ProductionStage.QC_REQUIRED: {
        ProductionStage.QC_COMPLETE: QC_ROLES,
    },
    ProductionStage.QC_COMPLETE: {
        ProductionStage.VALIDATION: QC_ROLES,
    },
    ProductionStage.VALIDATION: {
        ProductionStage.COMPLETED: SUPERVISOR_ROLES,
        ProductionStage.EXCEPTION: SUPERVISOR_ROLES,
    },
    ProductionStage.EXCEPTION: {
        ProductionStage.VALIDATION: SUPERVISOR_ROLES,
        ProductionStage.COMPLETED: SUPERVISOR_ROLES,
    },
}


def gate_requirements(run, target_stage):
    """Read-only list of what is still missing before a stage can be entered."""
    missing = []
    if target_stage == ProductionStage.DRAFT:
        if not run.factory_id:
            missing.append('Factory')
    elif target_stage == ProductionStage.INPUTS_COMPLETE:
        missing.extend(_input_gaps(run))
    elif target_stage == ProductionStage.PRODUCTION_ACTIVE:
        missing.extend(_input_gaps(run))
        if not run.started_at:
            missing.append('Started at')
    elif target_stage == ProductionStage.OUTPUT_RECORDED:
        if not run.pk or not run.outputs.exists():
            missing.append('At least one production output')
    elif target_stage == ProductionStage.QC_REQUIRED:
        if not run.pk or not run.outputs.exists():
            missing.append('At least one production output')
    elif target_stage == ProductionStage.QC_COMPLETE:
        missing.extend(_qc_gaps(run))
    elif target_stage == ProductionStage.VALIDATION:
        result = variance_for_run(run)
        if result['status'] == VARIANCE_INSUFFICIENT:
            missing.append('Expected, recorded, and QC verified quantities')
    elif target_stage == ProductionStage.COMPLETED:
        result = variance_for_run(run)
        if result['status'] == VARIANCE_INSUFFICIENT:
            missing.append('Variance result')
        elif result['status'] == VARIANCE_EXCEPTION and not _exception_accepted(run):
            missing.append('Variance exceeds tolerance and has not been accepted')
    elif target_stage == ProductionStage.EXCEPTION:
        result = variance_for_run(run)
        if result['status'] != VARIANCE_EXCEPTION:
            missing.append('Variance must exceed tolerance')
    elif target_stage == ProductionStage.CANCELLED:
        pass
    else:
        missing.append('Unknown stage')
    return {'ok': not missing, 'missing': missing}


def _input_gaps(run):
    missing = []
    if not run.product_id:
        missing.append('Product')
    if not run.variant_id:
        missing.append('Variant')
    if not run.packaging_id:
        missing.append('Packaging')
    if not run.production_line_id:
        missing.append('Production line')
    if not run.machine_id:
        missing.append('Machine')
    if run.planned_pack_quantity is None or run.planned_pack_quantity <= 0:
        missing.append('Planned pack quantity')
    return missing


def _qc_gaps(run):
    missing = []
    verification = _verification_or_none(run)
    if verification is None:
        return ['QC verification']
    if not verification.variant_id:
        missing.append('QC confirmed variant')
    if not verification.packaging_id:
        missing.append('QC confirmed packaging')
    from apps.production.variance import min_qc_photos_for

    minimum = min_qc_photos_for(run.factory)
    photo_count = verification.photos.count() if verification.pk else 0
    if photo_count < minimum:
        missing.append(f'At least {minimum} QC photo')
    if verification.qc_verified_quantity is None:
        missing.append('QC verified quantity')
    if verification.status != QCVerificationStatus.VERIFIED:
        missing.append('QC marked the run verified')
    return missing


def _verification_or_none(run):
    if not run.pk:
        return None
    try:
        return run.qc_verification
    except run.__class__.qc_verification.RelatedObjectDoesNotExist:
        return None


def _exception_accepted(run):
    from django.contrib.contenttypes.models import ContentType

    from apps.audit.models import AuditEvent

    if not run.pk:
        return False
    content_type = ContentType.objects.get_for_model(ProductionRun)
    return AuditEvent.objects.filter(
        target_content_type=content_type,
        target_object_id=run.pk,
        action=AuditAction.EXCEPTION_ACCEPTED,
    ).exists()


def transition(run, target, *, actor, reason='', enforce_role=True):
    if run.stage is None:
        raise ValidationError(
            'Legacy runs are not in the production control workflow.'
        )
    allowed = TRANSITIONS.get(run.stage, {})
    if target not in allowed:
        raise ValidationError(
            f'Cannot move from {run.stage} to {target}.'
        )
    if enforce_role and getattr(actor, 'role', None) not in allowed[target]:
        raise ValidationError('You cannot perform this transition.')

    with transaction.atomic():
        locked = ProductionRun.objects.select_for_update().select_related(
            'product', 'variant', 'packaging', 'factory',
        ).get(pk=run.pk)
        if locked.stage != run.stage:
            raise ValidationError('This run changed before the transition completed.')
        previous = locked.stage
        if target == ProductionStage.PRODUCTION_ACTIVE and locked.started_at is None:
            locked.started_at = timezone.now()
            locked.status = ProductionRunStatus.IN_PROGRESS
        gate = gate_requirements(locked, target)
        if not gate['ok']:
            raise ValidationError(
                'Still required: ' + '; '.join(gate['missing'])
            )
        locked.stage = target
        if target == ProductionStage.PRODUCTION_ACTIVE:
            locked.status = ProductionRunStatus.IN_PROGRESS
            if locked.started_at is None:
                locked.started_at = timezone.now()
        elif target == ProductionStage.COMPLETED:
            locked.status = ProductionRunStatus.COMPLETED
            if locked.ended_at is None:
                locked.ended_at = timezone.now()
        elif target == ProductionStage.CANCELLED:
            locked.status = ProductionRunStatus.CANCELLED
        locked.save()
        record_event(
            factory=locked.factory,
            actor=actor,
            action=AuditAction.STAGE_CHANGE,
            target=locked,
            field_name='stage',
            old_value=previous,
            new_value=target,
            reason=reason,
        )
        return locked


def create_controlled_run(
    user,
    *,
    product,
    variant,
    packaging,
    line,
    machine,
    planned_pack_quantity,
):
    if getattr(user, 'role', None) not in PRODUCTION_ROLES:
        raise ValidationError('You cannot configure a production run.')
    factory = _require_factory(user)
    now = timezone.now()
    with transaction.atomic():
        reference = allocate_reference(factory, now)
        run = ProductionRun.objects.create(
            factory=factory,
            production_line=line,
            machine=machine,
            created_by=user,
            reference=reference,
            status=ProductionRunStatus.PLANNED,
            stage=ProductionStage.DRAFT,
            product=product,
            variant=variant,
            packaging=packaging,
            planned_pack_quantity=planned_pack_quantity,
        )
        return transition(run, ProductionStage.INPUTS_COMPLETE, actor=user)


def store_validation_quantities(run):
    """Store expected quantity. Fill recorded quantity once, then leave it alone."""
    verification = _verification_or_none(run)
    if verification is None:
        raise ValidationError('QC verification is required before validation.')
    verification.expected_quantity = expected_individual_units(run)
    if verification.recorded_quantity is None:
        verification.recorded_quantity = recorded_quantity_for_run(run)
    verification.save()
    return verification


def validate_controlled_run(run, *, actor, enforce_role=True):
    """Move a QC-complete run through validation to completed or exception."""
    with transaction.atomic():
        locked = ProductionRun.objects.select_for_update().get(pk=run.pk)
        store_validation_quantities(locked)
        locked = transition(
            locked,
            ProductionStage.VALIDATION,
            actor=actor,
            enforce_role=enforce_role,
        )
        result = variance_for_run(locked)
        verification = locked.qc_verification
        if result['status'] == VARIANCE_EXCEPTION:
            verification.status = QCVerificationStatus.EXCEPTION
            verification.save()
            locked = transition(
                locked,
                ProductionStage.EXCEPTION,
                actor=actor,
                enforce_role=False,
                reason='Variance exceeds tolerance.',
            )
        elif result['status'] in RESOLVED_VARIANCE:
            locked = transition(
                locked,
                ProductionStage.COMPLETED,
                actor=actor,
                enforce_role=False,
            )
        return locked


def accept_variance(run, *, actor, reason):
    if getattr(actor, 'role', None) not in SUPERVISOR_ROLES:
        raise ValidationError('Only a supervisor or admin can accept a variance.')
    if not (reason or '').strip():
        raise ValidationError({'reason': 'A reason is required.'})
    if run.stage != ProductionStage.EXCEPTION:
        raise ValidationError('Only an exception run can be accepted.')
    with transaction.atomic():
        locked = ProductionRun.objects.select_for_update().get(pk=run.pk)
        record_event(
            factory=locked.factory,
            actor=actor,
            action=AuditAction.EXCEPTION_ACCEPTED,
            target=locked,
            field_name='stage',
            old_value=locked.stage,
            new_value=ProductionStage.COMPLETED,
            reason=reason,
        )
        return transition(
            locked,
            ProductionStage.COMPLETED,
            actor=actor,
            reason=reason,
        )


def revalidate_after_correction(run, *, actor, reason):
    if getattr(actor, 'role', None) not in (Role.SUPERVISOR, Role.ADMIN):
        raise ValidationError('Only a supervisor or admin can revalidate a run.')
    if run.stage != ProductionStage.EXCEPTION:
        raise ValidationError('Only an exception run can be revalidated.')
    with transaction.atomic():
        locked = ProductionRun.objects.select_for_update().get(pk=run.pk)
        verification = locked.qc_verification
        verification.expected_quantity = expected_individual_units(locked)
        verification.save()
        locked = transition(
            locked,
            ProductionStage.VALIDATION,
            actor=actor,
            reason=reason,
        )
        result = variance_for_run(locked)
        if result['status'] == VARIANCE_EXCEPTION:
            verification.status = QCVerificationStatus.EXCEPTION
            verification.save()
            return transition(
                locked,
                ProductionStage.EXCEPTION,
                actor=actor,
                enforce_role=False,
                reason=reason,
            )
        verification.status = QCVerificationStatus.VERIFIED
        verification.save()
        return transition(
            locked,
            ProductionStage.COMPLETED,
            actor=actor,
            enforce_role=False,
            reason=reason,
        )
