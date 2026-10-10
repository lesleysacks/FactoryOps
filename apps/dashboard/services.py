"""
FactoryOps Dashboard — Aggregations over existing operational records.

Reads materials, production, warehouse, and order models. Does not write
source records and does not introduce new inventory or fulfilment logic.
Date windows use UTC calendar dates (TIME_ZONE=UTC).
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from apps.materials.models import (
    MaterialAddition,
    MaterialConsumption,
    MaterialWaste,
    StockReconciliation,
    StockRecord,
)
from apps.orders.models import CustomerOrder, CustomerOrderFulfilmentStatus
from apps.production.models import (
    FinishedGoodDispatch,
    FinishedGoodReconciliation,
    FinishedGoodStockRecord,
    ProductionOutput,
    ProductionReject,
    ProductionRun,
    ProductionRunStatus,
)

ZERO = Decimal('0')
QUANTITY_QUANTUM = Decimal('0.001')
TREND_DAYS = 7


def _as_quantity(value):
    if value is None:
        return ZERO
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity_sum(queryset):
    total = queryset.aggregate(total=Sum('quantity'))['total']
    return _as_quantity(total)


def today():
    return timezone.now().date()


def trend_start(days=TREND_DAYS):
    return today() - timedelta(days=days - 1)


def _apply_factory(queryset, user, field='factory'):
    if user.factory_id:
        return queryset.filter(**{field: user.factory_id})
    return queryset


def daily_trend(queryset, date_field, user, factory_field, start, end):
    queryset = _apply_factory(queryset, user, factory_field)
    lookup = {f'{date_field}__date__gte': start, f'{date_field}__date__lte': end}
    date_key = f'{date_field}__date'
    rows = (
        queryset.filter(**lookup)
        .values(date_key)
        .annotate(total=Sum('quantity'))
    )
    by_date = {row[date_key]: _as_quantity(row['total']) for row in rows}
    series = []
    day = start
    while day <= end:
        series.append({'date': day, 'quantity': by_date.get(day, ZERO)})
        day += timedelta(days=1)
    return series


def operator_dashboard(user):
    current = today()
    runs_today = _apply_factory(ProductionRun.objects.all(), user).filter(
        started_at__date=current,
    ).select_related('factory').order_by('-started_at')
    planned_or_open = _apply_factory(ProductionRun.objects.all(), user).filter(
        status__in=[ProductionRunStatus.PLANNED, ProductionRunStatus.IN_PROGRESS],
    ).select_related('factory').order_by('status', 'reference')
    active_runs = _apply_factory(ProductionRun.objects.all(), user).filter(
        status=ProductionRunStatus.IN_PROGRESS,
    ).select_related('factory', 'production_line', 'machine').order_by('-started_at')
    completed_today = _apply_factory(ProductionRun.objects.all(), user).filter(
        status=ProductionRunStatus.COMPLETED,
        ended_at__date=current,
    ).select_related('factory', 'production_line', 'machine').order_by('-ended_at')
    consumption_today = _apply_factory(MaterialConsumption.objects.all(), user).filter(
        consumed_at__date=current,
    ).select_related('material', 'batch').order_by('-consumed_at')
    recent_additions = _apply_factory(MaterialAddition.objects.all(), user).select_related(
        'material', 'batch',
    ).order_by('-added_at')[:8]
    waste_today = _apply_factory(MaterialWaste.objects.all(), user).filter(
        occurred_at__date=current,
    ).select_related('material').order_by('-occurred_at')
    open_counts = _apply_factory(StockRecord.objects.all(), user).filter(
        closing_quantity__isnull=True,
    ).select_related('material').order_by('-recording_date')
    production_today = _apply_factory(
        ProductionOutput.objects.all(), user, 'production_run__factory',
    ).filter(recorded_at__date=current)
    open_run_count = planned_or_open.count()
    return {
        'today': current,
        'runs_today': list(runs_today[:12]),
        'open_runs': list(planned_or_open[:12]),
        'consumption_today': list(consumption_today[:12]),
        'consumption_total': _quantity_sum(consumption_today),
        'consumption_event_count': consumption_today.count(),
        'recent_additions': list(recent_additions),
        'waste_today': list(waste_today[:12]),
        'waste_total': _quantity_sum(waste_today),
        'open_stock_counts': list(open_counts[:8]),
        'open_run_count': open_run_count,
        'active_run_count': active_runs.count(),
        'active_runs': list(active_runs[:12]),
        'completed_runs_today': list(completed_today[:12]),
        'completed_run_count_today': completed_today.count(),
        'task_count': open_run_count + open_counts.count(),
        'production_total': _quantity_sum(production_today),
    }


def supervisor_dashboard(user):
    current = today()
    start = trend_start()
    active_runs = _apply_factory(ProductionRun.objects.all(), user).filter(
        status=ProductionRunStatus.IN_PROGRESS,
    ).select_related('factory').order_by('reference')
    output_today = _apply_factory(
        ProductionOutput.objects.all(), user, 'production_run__factory',
    ).filter(recorded_at__date=current)
    waste_today = _apply_factory(MaterialWaste.objects.all(), user).filter(
        occurred_at__date=current,
    )
    rejects_today = _apply_factory(
        ProductionReject.objects.all(), user, 'production_run__factory',
    ).filter(occurred_at__date=current)
    outstanding_material = _apply_factory(
        StockReconciliation.objects.all(), user,
    ).filter(calculated_at__isnull=True).select_related('material')
    outstanding_fg = _apply_factory(
        FinishedGoodReconciliation.objects.all(), user, 'warehouse__factory',
    ).filter(calculated_at__isnull=True).select_related('warehouse', 'finished_good')
    variances = _apply_factory(StockReconciliation.objects.all(), user).filter(
        calculated_at__isnull=False,
        variance_quantity__isnull=False,
    ).exclude(variance_quantity=ZERO).select_related('material').order_by('-reconciliation_date')
    output_trend = daily_trend(
        ProductionOutput.objects.all(),
        'recorded_at',
        user,
        'production_run__factory',
        start,
        current,
    )
    trend_max = max((row['quantity'] for row in output_trend), default=ZERO)
    for row in output_trend:
        row['percent'] = (
            int((row['quantity'] / trend_max) * 100) if trend_max else 0
        )
    return {
        'today': current,
        'active_runs': list(active_runs[:12]),
        'active_run_count': active_runs.count(),
        'output_today': _quantity_sum(output_today),
        'waste_today': _quantity_sum(waste_today),
        'rejects_today': _quantity_sum(rejects_today),
        'outstanding_material': list(outstanding_material[:8]),
        'outstanding_finished_goods': list(outstanding_fg[:8]),
        'recent_variances': list(variances[:8]),
        'variance_count': variances.count(),
        'output_trend': output_trend,
        'output_trend_max': trend_max,
    }


def manager_dashboard(user):
    current = today()
    start = trend_start()
    consumption_trend = daily_trend(
        MaterialConsumption.objects.all(), 'consumed_at', user, 'factory', start, current,
    )
    output_trend = daily_trend(
        ProductionOutput.objects.all(), 'recorded_at', user, 'production_run__factory', start, current,
    )
    waste_trend = daily_trend(
        MaterialWaste.objects.all(), 'occurred_at', user, 'factory', start, current,
    )
    variances = _apply_factory(StockReconciliation.objects.all(), user).filter(
        calculated_at__isnull=False,
        variance_quantity__isnull=False,
    ).exclude(variance_quantity=ZERO).select_related('material').order_by('-reconciliation_date')
    reconciliations = _apply_factory(
        StockReconciliation.objects.all(), user,
    ).filter(calculated_at__isnull=False).select_related('material').order_by('-reconciliation_date')
    fulfilment_counts = {
        status: _apply_factory(CustomerOrder.objects.all(), user).filter(
            fulfilment_status=status,
        ).count()
        for status, _label in CustomerOrderFulfilmentStatus.choices
    }
    dispatches = _apply_factory(
        FinishedGoodDispatch.objects.all(), user, 'warehouse__factory',
    ).filter(dispatched_at__date__gte=start).select_related(
        'warehouse', 'finished_good',
    ).order_by('-dispatched_at')
    return {
        'today': current,
        'consumption_trend': consumption_trend,
        'output_trend': output_trend,
        'waste_trend': waste_trend,
        'consumption_total': sum((row['quantity'] for row in consumption_trend), ZERO),
        'output_total': sum((row['quantity'] for row in output_trend), ZERO),
        'waste_total': sum((row['quantity'] for row in waste_trend), ZERO),
        'recent_variances': list(variances[:8]),
        'reconciliation_history': list(reconciliations[:8]),
        'fulfilment_counts': fulfilment_counts,
        'fulfilled_orders': fulfilment_counts.get(
            CustomerOrderFulfilmentStatus.FULFILLED, 0,
        ),
        'recent_dispatches': list(dispatches[:8]),
    }


def executive_dashboard(user):
    current = today()
    start = trend_start()
    output_total = _quantity_sum(_apply_factory(
        ProductionOutput.objects.all(), user, 'production_run__factory',
    ).filter(recorded_at__date__gte=start, recorded_at__date__lte=current))
    consumption_total = _quantity_sum(_apply_factory(
        MaterialConsumption.objects.all(), user,
    ).filter(consumed_at__date__gte=start, consumed_at__date__lte=current))
    waste_total = _quantity_sum(_apply_factory(
        MaterialWaste.objects.all(), user,
    ).filter(occurred_at__date__gte=start, occurred_at__date__lte=current))
    reject_total = _quantity_sum(_apply_factory(
        ProductionReject.objects.all(), user, 'production_run__factory',
    ).filter(occurred_at__date__gte=start, occurred_at__date__lte=current))
    fulfilment_counts = {
        status: _apply_factory(CustomerOrder.objects.all(), user).filter(
            fulfilment_status=status,
        ).count()
        for status, _label in CustomerOrderFulfilmentStatus.choices
    }
    significant_variances = _apply_factory(
        StockReconciliation.objects.all(), user,
    ).filter(
        calculated_at__isnull=False,
        variance_quantity__isnull=False,
        reconciliation_date__gte=start,
    ).exclude(variance_quantity=ZERO).select_related('material', 'factory').order_by(
        '-reconciliation_date',
    )
    return {
        'today': current,
        'period_start': start,
        'output_total': output_total,
        'consumption_total': consumption_total,
        'waste_total': waste_total,
        'reject_total': reject_total,
        'fulfilment_counts': fulfilment_counts,
        'significant_variances': list(significant_variances[:8]),
        'unfulfilled_orders': fulfilment_counts.get(
            CustomerOrderFulfilmentStatus.UNFULFILLED, 0,
        ),
        'fulfilled_orders': fulfilment_counts.get(
            CustomerOrderFulfilmentStatus.FULFILLED, 0,
        ),
        'variance_count': significant_variances.count(),
    }


def _latest_by_key(queryset, key_func):
    latest = {}
    for record in queryset:
        key = key_func(record)
        if key not in latest:
            latest[key] = record
    return list(latest.values())


def inventory_dashboard(user):
    current = today()
    material_records = _apply_factory(
        StockRecord.objects.all(), user,
    ).select_related('material', 'factory').order_by('-recording_date', '-id')
    fg_records = _apply_factory(
        FinishedGoodStockRecord.objects.all(), user, 'warehouse__factory',
    ).select_related('warehouse', 'finished_good').order_by('-recording_date', '-id')
    additions = _apply_factory(MaterialAddition.objects.all(), user).filter(
        added_at__date=current,
    ).select_related('material')
    consumption = _apply_factory(MaterialConsumption.objects.all(), user).filter(
        consumed_at__date=current,
    ).select_related('material')
    exceptions = _apply_factory(StockReconciliation.objects.all(), user).filter(
        calculated_at__isnull=False,
        variance_quantity__isnull=False,
    ).exclude(variance_quantity=ZERO).select_related('material').order_by('-reconciliation_date')
    dispatches = _apply_factory(
        FinishedGoodDispatch.objects.all(), user, 'warehouse__factory',
    ).select_related('warehouse', 'finished_good').order_by('-dispatched_at')
    material_snapshots = _latest_by_key(
        material_records, lambda rec: (rec.factory_id, rec.material_id),
    )[:20]
    return {
        'today': current,
        'material_snapshots': material_snapshots,
        'stock_item_count': len(material_snapshots),
        'warehouse_snapshots': _latest_by_key(
            fg_records, lambda rec: (rec.warehouse_id, rec.finished_good_id),
        )[:20],
        'additions_today': list(additions[:10]),
        'additions_total': _quantity_sum(additions),
        'consumption_today': list(consumption[:10]),
        'consumption_total': _quantity_sum(consumption),
        'reconciliation_exceptions': list(exceptions[:10]),
        'exception_count': exceptions.count(),
        'recent_dispatches': list(dispatches[:10]),
    }
