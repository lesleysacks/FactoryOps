"""
FactoryOps Production — Finished-goods reconciliation calculations.

Expected closing for a warehouse/finished good/date:

    opening + additions + adjustment increases − adjustment decreases − dispatches

Date boundary: event DateTimeFields are stored in UTC (TIME_ZONE=UTC).
An event is included when its UTC calendar date equals reconciliation_date.
FinishedGoodStockRecord.recording_date is already a DateField and matches
that same date.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

from apps.production.models import (
    FinishedGoodAddition,
    FinishedGoodAdjustment,
    FinishedGoodAdjustmentType,
    FinishedGoodDispatch,
    FinishedGoodStockRecord,
)

ZERO = Decimal('0')
QUANTITY_QUANTUM = Decimal('0.001')


def _as_quantity(value):
    if value is None:
        return ZERO
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity_sum(queryset):
    total = queryset.aggregate(total=Sum('quantity'))['total']
    return _as_quantity(total)


def calculate_expected_closing(warehouse, finished_good, reconciliation_date):
    stock_record = FinishedGoodStockRecord.objects.filter(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=reconciliation_date,
    ).first()
    if stock_record is None:
        raise ValidationError({
            'reconciliation_date': (
                'A stock record is required for this warehouse, finished good, and date.'
            ),
        })

    scope = {
        'warehouse': warehouse,
        'finished_good': finished_good,
    }
    additions = _quantity_sum(FinishedGoodAddition.objects.filter(
        **scope,
        added_at__date=reconciliation_date,
    ))
    increases = _quantity_sum(FinishedGoodAdjustment.objects.filter(
        **scope,
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at__date=reconciliation_date,
    ))
    decreases = _quantity_sum(FinishedGoodAdjustment.objects.filter(
        **scope,
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at__date=reconciliation_date,
    ))
    dispatches = _quantity_sum(FinishedGoodDispatch.objects.filter(
        **scope,
        dispatched_at__date=reconciliation_date,
    ))
    expected = _as_quantity(
        stock_record.opening_quantity
        + additions
        + increases
        - decreases
        - dispatches
    )
    actual = (
        _as_quantity(stock_record.closing_quantity)
        if stock_record.closing_quantity is not None
        else None
    )
    variance = _as_quantity(actual - expected) if actual is not None else None
    return {
        'opening_quantity': stock_record.opening_quantity,
        'additions': additions,
        'adjustment_increases': increases,
        'adjustment_decreases': decreases,
        'dispatches': dispatches,
        'expected_closing_quantity': expected,
        'actual_closing_quantity': actual,
        'variance_quantity': variance,
    }


def reconcile_finished_goods(reconciliation):
    result = calculate_expected_closing(
        reconciliation.warehouse,
        reconciliation.finished_good,
        reconciliation.reconciliation_date,
    )
    reconciliation.expected_closing_quantity = result['expected_closing_quantity']
    reconciliation.actual_closing_quantity = result['actual_closing_quantity']
    reconciliation.variance_quantity = result['variance_quantity']
    reconciliation.calculated_at = timezone.now()
    reconciliation.save()
    return reconciliation
