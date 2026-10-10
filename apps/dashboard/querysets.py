"""
FactoryOps — Operator capture querysets.

Factory isolation is enforced in querysets, not by trusting posted IDs.
"""

from django.db.models import Sum

from apps.factories.models import ProductionLine
from apps.machines.models import Machine
from apps.materials.models import Material, MaterialBatch, StockRecord
from apps.production.models import ProductionRun, ProductionRunStatus


def user_factory(user):
    return getattr(user, 'factory', None)


def active_materials_for(user):
    factory = user_factory(user)
    if factory is None:
        return Material.objects.none()
    return Material.objects.filter(factory=factory, is_active=True).order_by('code')


def active_lines_for(user):
    factory = user_factory(user)
    if factory is None:
        return ProductionLine.objects.none()
    return ProductionLine.objects.filter(factory=factory, is_active=True).order_by('name')


def active_machines_for(user):
    factory = user_factory(user)
    if factory is None:
        return Machine.objects.none()
    return (
        Machine.objects.filter(
            production_line__factory=factory,
            production_line__is_active=True,
            is_active=True,
        )
        .select_related('production_line')
        .order_by('production_line__name', 'code')
    )


def open_stock_counts_for(user):
    factory = user_factory(user)
    if factory is None:
        return StockRecord.objects.none()
    return (
        StockRecord.objects.filter(factory=factory, closing_quantity__isnull=True)
        .select_related('material')
        .order_by('-recording_date', 'material__code')
    )


def production_runs_for(user):
    factory = user_factory(user)
    if factory is None:
        return ProductionRun.objects.none()
    return (
        ProductionRun.objects.filter(factory=factory)
        .select_related('factory', 'production_line', 'machine', 'created_by')
        .annotate(output_total=Sum('outputs__quantity'))
    )


def active_production_runs_for(user):
    return production_runs_for(user).filter(
        status=ProductionRunStatus.IN_PROGRESS,
    ).order_by('-started_at')


def completed_production_runs_today_for(user, day):
    return production_runs_for(user).filter(
        status=ProductionRunStatus.COMPLETED,
        ended_at__date=day,
    ).order_by('-ended_at')


def active_machines_on_line_for(user, line):
    return active_machines_for(user).filter(production_line=line)


def batches_for_material(user, material):
    factory = user_factory(user)
    if factory is None or material is None:
        return MaterialBatch.objects.none()
    if material.factory_id != factory.id or not material.is_active:
        return MaterialBatch.objects.none()
    return MaterialBatch.objects.filter(material=material).order_by('lot_number')
