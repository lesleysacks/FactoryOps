"""
FactoryOps Materials — Operator consumption capture.

Appends MaterialConsumption events against a ProductionRun.
Does not mutate StockRecord or MaterialAddition.
Does not record waste, QC, or reconciliation.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.materials.models import MaterialConsumption
from apps.production.models import ProductionRun, ProductionRunStatus


def _require_factory(user):
    factory = getattr(user, 'factory', None)
    if factory is None:
        raise ValidationError(
            'Your account is not assigned to a factory. Ask a supervisor to assign you.'
        )
    if not factory.is_active:
        raise ValidationError('Cannot record consumption for an inactive factory.')
    return factory


def record_material_consumption(user, run_id, material, batch, quantity):
    factory = _require_factory(user)
    if material is None:
        raise ValidationError({'material': 'Select a material.'})
    if not material.is_active:
        raise ValidationError({'material': 'This material is not available.'})
    if material.factory_id != factory.id:
        raise ValidationError({'material': 'This material does not belong to your factory.'})
    if batch is None:
        raise ValidationError({'batch': 'Select a batch.'})
    if batch.material_id != material.id:
        raise ValidationError({'batch': 'This batch does not belong to the selected material.'})
    if batch.material.factory_id != factory.id:
        raise ValidationError({'batch': 'This batch does not belong to your factory.'})

    with transaction.atomic():
        try:
            run = ProductionRun.objects.select_for_update().get(pk=run_id)
        except ProductionRun.DoesNotExist:
            raise
        if run.factory_id != factory.id:
            raise ProductionRun.DoesNotExist
        if run.status != ProductionRunStatus.IN_PROGRESS:
            raise ValidationError(
                'Consumption can only be recorded on an active run.'
            )
        return MaterialConsumption.objects.create(
            factory=factory,
            material=material,
            batch=batch,
            quantity=quantity,
            production_run=run,
            recorded_by=user,
            consumed_at=timezone.now(),
        )
