"""
FactoryOps Materials — Reconciliation calculations.

Expected closing for a factory/material/date:

    opening + additions − consumption − waste − scrap

Date boundary: event DateTimeFields are stored in UTC (TIME_ZONE=UTC).
An event is included when its UTC calendar date equals reconciliation_date.
StockRecord.recording_date is already a DateField and matches that same date.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

from apps.materials.models import (
    MaterialAddition,
    MaterialConsumption,
    MaterialScrap,
    MaterialWaste,
    StockRecord,
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


def calculate_expected_closing(factory, material, reconciliation_date):
    stock_record = StockRecord.objects.filter(
        factory=factory,
        material=material,
        recording_date=reconciliation_date,
    ).first()
    if stock_record is None:
        raise ValidationError({
            'reconciliation_date': (
                'A stock record is required for this factory, material, and date.'
            ),
        })

    scope = {
        'factory': factory,
        'material': material,
    }
    additions = _quantity_sum(MaterialAddition.objects.filter(
        **scope,
        added_at__date=reconciliation_date,
    ))
    consumption = _quantity_sum(MaterialConsumption.objects.filter(
        **scope,
        consumed_at__date=reconciliation_date,
    ))
    waste = _quantity_sum(MaterialWaste.objects.filter(
        **scope,
        occurred_at__date=reconciliation_date,
    ))
    scrap = _quantity_sum(MaterialScrap.objects.filter(
        **scope,
        occurred_at__date=reconciliation_date,
    ))
    expected = _as_quantity(
        stock_record.opening_quantity
        + additions
        - consumption
        - waste
        - scrap
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
        'consumption': consumption,
        'waste': waste,
        'scrap': scrap,
        'expected_closing_quantity': expected,
        'actual_closing_quantity': actual,
        'variance_quantity': variance,
    }


def reconcile_stock(reconciliation):
    result = calculate_expected_closing(
        reconciliation.factory,
        reconciliation.material,
        reconciliation.reconciliation_date,
    )
    reconciliation.expected_closing_quantity = result['expected_closing_quantity']
    reconciliation.actual_closing_quantity = result['actual_closing_quantity']
    reconciliation.variance_quantity = result['variance_quantity']
    reconciliation.calculated_at = timezone.now()
    reconciliation.save()
    return reconciliation
