"""
FactoryOps Production — Operator floor workflow.

Starts, records output on, completes ProductionRun records,
and records machine material-state snapshots.
Does not record consumption, waste, rejects, or QC.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.production.models import (
    ProductionOutput,
    ProductionRun,
    ProductionRunMaterialState,
    ProductionRunStatus,
)


def _require_factory(user):
    factory = getattr(user, 'factory', None)
    if factory is None:
        raise ValidationError(
            'Your account is not assigned to a factory. Ask a supervisor to assign you.'
        )
    if not factory.is_active:
        raise ValidationError('Cannot record production for an inactive factory.')
    return factory


def allocate_reference(factory, when=None):
    when = when or timezone.now()
    prefix = f"PR-{when.date().strftime('%Y%m%d')}-"
    last = (
        ProductionRun.objects.select_for_update()
        .filter(factory=factory, reference__startswith=prefix)
        .order_by('-reference')
        .first()
    )
    seq = 1
    if last and last.reference.startswith(prefix):
        suffix = last.reference[len(prefix):]
        if suffix.isdigit():
            seq = int(suffix) + 1
        else:
            seq = (
                ProductionRun.objects.filter(
                    factory=factory, reference__startswith=prefix,
                ).count()
                + 1
            )
    return f'{prefix}{seq:03d}'


def start_production_run(user, machine, line=None):
    factory = _require_factory(user)
    if machine is None:
        raise ValidationError({'machine': 'Select a machine.'})
    if not machine.is_active:
        raise ValidationError({'machine': 'This machine is not available.'})
    machine_line = machine.production_line
    if machine_line.factory_id != factory.id:
        raise ValidationError({'machine': 'This machine does not belong to your factory.'})
    if not machine_line.is_active:
        raise ValidationError({'machine': 'This production line is not available.'})
    if line is not None and machine.production_line_id != line.id:
        raise ValidationError({
            'machine': 'This machine does not belong to the selected production line.',
        })
    if line is not None and line.factory_id != factory.id:
        raise ValidationError({'machine': 'This production line does not belong to your factory.'})

    now = timezone.now()
    with transaction.atomic():
        reference = allocate_reference(factory, now)
        return ProductionRun.objects.create(
            factory=factory,
            production_line=machine_line,
            machine=machine,
            created_by=user,
            reference=reference,
            status=ProductionRunStatus.IN_PROGRESS,
            started_at=now,
        )


def record_production_output(user, run_id, quantity, output_name):
    factory = _require_factory(user)
    name = (output_name or '').strip()
    if not name:
        raise ValidationError({'output_name': 'Describe what was produced.'})
    with transaction.atomic():
        try:
            run = ProductionRun.objects.select_for_update().get(pk=run_id)
        except ProductionRun.DoesNotExist:
            raise
        if run.factory_id != factory.id:
            raise ProductionRun.DoesNotExist
        if run.status != ProductionRunStatus.IN_PROGRESS:
            raise ValidationError('Output can only be recorded on an active run.')
        return ProductionOutput.objects.create(
            production_run=run,
            output_name=name,
            quantity=quantity,
            recorded_at=timezone.now(),
        )


def complete_production_run(user, run_id):
    factory = _require_factory(user)
    with transaction.atomic():
        try:
            run = ProductionRun.objects.select_for_update().get(pk=run_id)
        except ProductionRun.DoesNotExist:
            raise
        if run.factory_id != factory.id:
            raise ProductionRun.DoesNotExist
        if run.status == ProductionRunStatus.COMPLETED:
            raise ValidationError('This run is already completed.')
        if run.status != ProductionRunStatus.IN_PROGRESS:
            raise ValidationError('Only an active run can be completed.')
        run.status = ProductionRunStatus.COMPLETED
        run.ended_at = timezone.now()
        run.save()
        return run


def record_material_state(user, run_id, material, roll_quantity, spare_roll_quantity):
    factory = _require_factory(user)
    if material is None:
        raise ValidationError({'material': 'Select a material.'})
    if not material.is_active:
        raise ValidationError({'material': 'This material is not available.'})
    if material.factory_id != factory.id:
        raise ValidationError({'material': 'This material does not belong to your factory.'})
    with transaction.atomic():
        try:
            run = ProductionRun.objects.select_for_update().get(pk=run_id)
        except ProductionRun.DoesNotExist:
            raise
        if run.factory_id != factory.id:
            raise ProductionRun.DoesNotExist
        if run.status != ProductionRunStatus.IN_PROGRESS:
            raise ValidationError(
                'Material state can only be recorded on an active run.'
            )
        return ProductionRunMaterialState.objects.create(
            production_run=run,
            material=material,
            roll_quantity=roll_quantity,
            spare_roll_quantity=spare_roll_quantity,
            recorded_by=user,
            recorded_at=timezone.now(),
        )


def current_material_states_for(run):
    snapshots = (
        run.material_states.select_related('material', 'recorded_by')
        .order_by('material_id', '-recorded_at', '-pk')
    )
    current = []
    seen = set()
    for snapshot in snapshots:
        if snapshot.material_id in seen:
            continue
        seen.add(snapshot.material_id)
        current.append(snapshot)
    current.sort(key=lambda item: item.material.code)
    return current
