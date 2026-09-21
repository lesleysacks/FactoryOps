"""
Tests for Production App — M10 Finished Goods Reconciliation & Dispatch
"""

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.factories.models import Factory
from apps.production.models import (
    FinishedGood,
    FinishedGoodAddition,
    FinishedGoodAdjustment,
    FinishedGoodAdjustmentType,
    FinishedGoodDispatch,
    FinishedGoodReconciliation,
    FinishedGoodStockRecord,
    Warehouse,
)


@pytest.fixture
def finished_good(db, factory):
    return FinishedGood.objects.create(
        factory=factory,
        code='CRATE-001',
        name='Plastic Crates',
        description='Injection-moulded crates',
    )


@pytest.fixture
def warehouse(db, factory):
    return Warehouse.objects.create(
        factory=factory,
        code='FG-MAIN',
        name='Finished Goods Main Store',
    )


@pytest.fixture
def fg_stock_record(db, warehouse, finished_good):
    return FinishedGoodStockRecord.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('100.000'),
        closing_quantity=Decimal('110.000'),
    )


@pytest.fixture
def fg_reconciliation(db, warehouse, finished_good):
    return FinishedGoodReconciliation.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        reconciliation_date=date(2026, 10, 1),
        notes='End of day finished-goods count',
    )


@pytest.mark.django_db
def test_dispatch_creation(warehouse, finished_good):
    dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
        reference='FG-OUT-001',
        notes='Goods left warehouse inventory',
    )
    assert dispatch.warehouse == warehouse
    assert dispatch.finished_good == finished_good
    assert dispatch.quantity == Decimal('100.000')
    assert dispatch.reference == 'FG-OUT-001'
    assert dispatch.notes == 'Goods left warehouse inventory'
    assert dispatch.created_at is not None
    assert dispatch.updated_at is not None
    assert warehouse.dispatches.count() == 1
    assert finished_good.dispatches.count() == 1


@pytest.mark.django_db
def test_dispatch_quantity_validation(warehouse, finished_good):
    zero = FinishedGoodDispatch(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('0.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        zero.save()
    assert 'quantity' in extra_info.value.message_dict

    negative = FinishedGoodDispatch(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('-25.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        negative.save()
    assert 'quantity' in extra_info.value.message_dict


@pytest.mark.django_db
def test_dispatch_factory_integrity(warehouse, finished_good):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_good = FinishedGood.objects.create(
        factory=other_factory,
        code='CRATE-SOUTH',
        name='South Crates',
    )
    dispatch = FinishedGoodDispatch(
        warehouse=warehouse,
        finished_good=other_good,
        quantity=Decimal('10.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        dispatch.save()
    assert 'finished_good' in extra_info.value.message_dict


@pytest.mark.django_db
def test_historical_dispatches_remain_separate(warehouse, finished_good):
    morning = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
        reference='FG-OUT-0800',
    )
    midday = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('50.000'),
        dispatched_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
        reference='FG-OUT-1100',
    )
    afternoon = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('25.000'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
        reference='FG-OUT-1500',
    )
    assert morning.pk != midday.pk != afternoon.pk
    quantities = list(
        FinishedGoodDispatch.objects.filter(finished_good=finished_good)
        .order_by('dispatched_at')
        .values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('100.000'), Decimal('50.000'), Decimal('25.000')]
    assert FinishedGoodDispatch.objects.filter(finished_good=finished_good).count() == 3


@pytest.mark.django_db
def test_dispatch_str(warehouse, finished_good):
    dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    assert str(dispatch) == 'FG-MAIN — CRATE-001 — 100.000'


@pytest.mark.django_db
def test_inactive_warehouse_dispatch_rejected(warehouse, finished_good):
    warehouse.is_active = False
    warehouse.save()
    dispatch = FinishedGoodDispatch(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        dispatch.save()
    assert 'warehouse' in extra_info.value.message_dict


@pytest.mark.django_db
def test_expected_closing_calculation(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Found crates',
    )
    FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('5.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Damaged crates',
    )
    FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('20.000'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    fg_reconciliation.refresh_from_db()
    assert fg_reconciliation.expected_closing_quantity == Decimal('135.000')
    assert fg_reconciliation.calculated_at is not None


@pytest.mark.django_db
def test_adjustment_increase_inclusion(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('15.000'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Found crates',
    )
    fg_reconciliation.calculate()
    assert fg_reconciliation.expected_closing_quantity == Decimal('115.000')


@pytest.mark.django_db
def test_adjustment_decrease_inclusion(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('8.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Damaged crates',
    )
    fg_reconciliation.calculate()
    assert fg_reconciliation.expected_closing_quantity == Decimal('92.000')


@pytest.mark.django_db
def test_dispatch_inclusion(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('30.000'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    assert fg_reconciliation.expected_closing_quantity == Decimal('70.000')


@pytest.mark.django_db
def test_variance_calculation(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Found crates',
    )
    FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('5.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Damaged crates',
    )
    FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('20.000'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    fg_reconciliation.refresh_from_db()
    assert fg_reconciliation.actual_closing_quantity == Decimal('110.000')
    assert fg_reconciliation.expected_closing_quantity == Decimal('135.000')
    assert fg_reconciliation.variance_quantity == Decimal('-25.000')


@pytest.mark.django_db
def test_reconciliation_decimal_accuracy(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('0.125'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('0.050'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    assert fg_reconciliation.expected_closing_quantity == Decimal('100.075')
    assert fg_reconciliation.variance_quantity == Decimal('9.925')


@pytest.mark.django_db
def test_reconciliation_does_not_alter_source_records(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    addition = FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    increase = FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Found crates',
    )
    decrease = FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('5.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Damaged crates',
    )
    dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('20.000'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    fg_stock_record.refresh_from_db()
    addition.refresh_from_db()
    increase.refresh_from_db()
    decrease.refresh_from_db()
    dispatch.refresh_from_db()
    assert fg_stock_record.opening_quantity == Decimal('100.000')
    assert fg_stock_record.closing_quantity == Decimal('110.000')
    assert addition.quantity == Decimal('50.000')
    assert increase.quantity == Decimal('10.000')
    assert decrease.quantity == Decimal('5.000')
    assert dispatch.quantity == Decimal('20.000')
    assert FinishedGoodStockRecord.objects.filter(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
    ).count() == 1


@pytest.mark.django_db
def test_reconciliation_string_representation(fg_reconciliation):
    assert str(fg_reconciliation) == 'FG-MAIN — CRATE-001 — 2026-10-01'


@pytest.mark.django_db
def test_reconciliation_requires_stock_record(fg_reconciliation):
    with pytest.raises(ValidationError) as extra_info:
        fg_reconciliation.calculate()
    assert 'reconciliation_date' in extra_info.value.message_dict


@pytest.mark.django_db
def test_reconciliation_without_closing_quantity(
    warehouse, finished_good, fg_reconciliation
):
    FinishedGoodStockRecord.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('100.000'),
    )
    fg_reconciliation.calculate()
    fg_reconciliation.refresh_from_db()
    assert fg_reconciliation.expected_closing_quantity == Decimal('100.000')
    assert fg_reconciliation.actual_closing_quantity is None
    assert fg_reconciliation.variance_quantity is None


@pytest.mark.django_db
def test_positive_variance_when_actual_exceeds_expected(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    assert fg_reconciliation.expected_closing_quantity == Decimal('90.000')
    assert fg_reconciliation.actual_closing_quantity == Decimal('110.000')
    assert fg_reconciliation.variance_quantity == Decimal('20.000')


@pytest.mark.django_db
def test_reconciliation_excludes_events_on_other_dates(
    warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 2, 9, 0, tzinfo=dt_timezone.utc),
    )
    FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        dispatched_at=datetime(2026, 9, 30, 15, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    assert fg_reconciliation.expected_closing_quantity == Decimal('100.000')


@pytest.mark.django_db
def test_reconciliation_excludes_unrelated_warehouse(
    factory, warehouse, finished_good, fg_stock_record, fg_reconciliation
):
    other_warehouse = Warehouse.objects.create(
        factory=factory,
        code='FG-STORE',
        name='Finished Goods Store',
    )
    FinishedGoodAddition.objects.create(
        warehouse=other_warehouse,
        finished_good=finished_good,
        quantity=Decimal('999.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    fg_reconciliation.calculate()
    assert fg_reconciliation.expected_closing_quantity == Decimal('100.000')
