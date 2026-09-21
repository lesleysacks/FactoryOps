"""
Tests for Production App — M9 Finished Goods Inventory & Warehouse Foundations
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
    FinishedGoodReconciliation,
    FinishedGoodStockRecord,
    ProductionOutput,
    ProductionRun,
    ProductionRunStatus,
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
        description='Primary finished-goods warehouse',
    )


@pytest.fixture
def fg_stock_record(db, warehouse, finished_good):
    return FinishedGoodStockRecord.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('800.000'),
        closing_quantity=Decimal('1575.000'),
    )


@pytest.fixture
def production_run(db, factory):
    return ProductionRun.objects.create(
        factory=factory,
        reference='PR-20261001-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )


@pytest.fixture
def production_output(db, production_run, finished_good):
    return ProductionOutput.objects.create(
        production_run=production_run,
        output_name='Plastic Crates',
        finished_good=finished_good,
        quantity=Decimal('500.000'),
        recorded_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )


@pytest.mark.django_db
def test_warehouse_creation(warehouse, factory):
    assert warehouse.factory == factory
    assert warehouse.code == 'FG-MAIN'
    assert warehouse.name == 'Finished Goods Main Store'
    assert warehouse.description == 'Primary finished-goods warehouse'
    assert warehouse.is_active is True
    assert warehouse.created_at is not None
    assert warehouse.updated_at is not None
    assert factory.warehouses.count() == 1


@pytest.mark.django_db
def test_warehouse_code_unique_per_factory(factory, warehouse):
    duplicate = Warehouse(
        factory=factory,
        code='FG-MAIN',
        name='Duplicate Store',
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_same_warehouse_code_allowed_across_factories(factory, warehouse):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other = Warehouse.objects.create(
        factory=other_factory,
        code='FG-MAIN',
        name='South Finished Goods Store',
    )
    assert other.code == warehouse.code
    assert other.factory != warehouse.factory
    assert Warehouse.objects.filter(code='FG-MAIN').count() == 2


@pytest.mark.django_db
def test_warehouse_example_codes(factory):
    Warehouse.objects.create(factory=factory, code='FG-MAIN', name='Main Store')
    Warehouse.objects.create(factory=factory, code='FG-STORE', name='Store')
    Warehouse.objects.create(factory=factory, code='FG-HOLDING', name='Holding')
    assert factory.warehouses.count() == 3


@pytest.mark.django_db
def test_inactive_factory_warehouse_rejected(factory):
    factory.is_active = False
    factory.save()
    warehouse = Warehouse(
        factory=factory,
        code='FG-MAIN',
        name='Finished Goods Main Store',
    )
    with pytest.raises(ValidationError) as extra_info:
        warehouse.save()
    assert 'factory' in extra_info.value.message_dict


@pytest.mark.django_db
def test_warehouse_str(warehouse):
    assert str(warehouse) == 'Main Factory — FG-MAIN'


@pytest.mark.django_db
def test_finished_good_stock_record_creation(fg_stock_record, warehouse, finished_good):
    assert fg_stock_record.warehouse == warehouse
    assert fg_stock_record.finished_good == finished_good
    assert fg_stock_record.recording_date == date(2026, 10, 1)
    assert fg_stock_record.opening_quantity == Decimal('800.000')
    assert fg_stock_record.closing_quantity == Decimal('1575.000')
    assert fg_stock_record.created_at is not None
    assert fg_stock_record.updated_at is not None
    assert warehouse.stock_records.count() == 1
    assert finished_good.stock_records.count() == 1
    assert not hasattr(finished_good, 'current_quantity')


@pytest.mark.django_db
def test_finished_good_addition_creation(warehouse, finished_good, production_output):
    addition = FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('500.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        production_output=production_output,
    )
    assert addition.warehouse == warehouse
    assert addition.finished_good == finished_good
    assert addition.quantity == Decimal('500.000')
    assert addition.production_output == production_output
    assert addition.created_at is not None
    assert warehouse.additions.count() == 1
    assert finished_good.additions.count() == 1
    assert production_output.stock_additions.count() == 1


@pytest.mark.django_db
def test_finished_good_addition_without_production_output(warehouse, finished_good):
    addition = FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('300.000'),
        added_at=datetime(2026, 10, 1, 14, 0, tzinfo=dt_timezone.utc),
    )
    assert addition.production_output_id is None
    assert addition.quantity == Decimal('300.000')


@pytest.mark.django_db
def test_finished_good_adjustment_creation(warehouse, finished_good):
    adjustment = FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('25.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 17, 0, tzinfo=dt_timezone.utc),
        reason='Damaged crates removed from store',
    )
    assert adjustment.warehouse == warehouse
    assert adjustment.finished_good == finished_good
    assert adjustment.quantity == Decimal('25.000')
    assert adjustment.adjustment_type == FinishedGoodAdjustmentType.DECREASE
    assert adjustment.reason == 'Damaged crates removed from store'
    assert warehouse.adjustments.count() == 1
    assert finished_good.adjustments.count() == 1


@pytest.mark.django_db
def test_adjustment_type_must_be_increase_or_decrease(warehouse, finished_good):
    adjustment = FinishedGoodAdjustment(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        adjustment_type='TRANSFER',
        occurred_at=datetime(2026, 10, 1, 17, 0, tzinfo=dt_timezone.utc),
        reason='Invalid type',
    )
    with pytest.raises(ValidationError) as extra_info:
        adjustment.save()
    assert 'adjustment_type' in extra_info.value.message_dict


@pytest.mark.django_db
def test_factory_mismatch_rejected(factory, warehouse, finished_good):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_good = FinishedGood.objects.create(
        factory=other_factory,
        code='CRATE-SOUTH',
        name='South Crates',
    )
    record = FinishedGoodStockRecord(
        warehouse=warehouse,
        finished_good=other_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('8.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        record.save()
    assert 'finished_good' in extra_info.value.message_dict

    addition = FinishedGoodAddition(
        warehouse=warehouse,
        finished_good=other_good,
        quantity=Decimal('100.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        addition.save()
    assert 'finished_good' in extra_info.value.message_dict

    adjustment = FinishedGoodAdjustment(
        warehouse=warehouse,
        finished_good=other_good,
        quantity=Decimal('5.000'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=datetime(2026, 10, 1, 17, 0, tzinfo=dt_timezone.utc),
        reason='Count correction',
    )
    with pytest.raises(ValidationError) as extra_info:
        adjustment.save()
    assert 'finished_good' in extra_info.value.message_dict


@pytest.mark.django_db
def test_quantity_validation(warehouse, finished_good):
    negative_record = FinishedGoodStockRecord(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('-1.000'),
        closing_quantity=Decimal('10.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        negative_record.save()
    assert 'opening_quantity' in extra_info.value.message_dict

    negative_closing = FinishedGoodStockRecord(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 2),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('-5.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        negative_closing.save()
    assert 'closing_quantity' in extra_info.value.message_dict

    zero_addition = FinishedGoodAddition(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('0.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        zero_addition.save()
    assert 'quantity' in extra_info.value.message_dict

    negative_addition = FinishedGoodAddition(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('-10.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        negative_addition.save()
    assert 'quantity' in extra_info.value.message_dict

    negative_adjustment = FinishedGoodAdjustment(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('-25.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 17, 0, tzinfo=dt_timezone.utc),
        reason='Negative not allowed',
    )
    with pytest.raises(ValidationError) as extra_info:
        negative_adjustment.save()
    assert 'quantity' in extra_info.value.message_dict

    zero_record = FinishedGoodStockRecord.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 3),
        opening_quantity=Decimal('0.000'),
        closing_quantity=Decimal('0.000'),
    )
    assert zero_record.opening_quantity == Decimal('0.000')
    assert zero_record.closing_quantity == Decimal('0.000')


@pytest.mark.django_db
def test_historical_events_remain_separate(warehouse, finished_good):
    morning = FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('500.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    afternoon = FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('300.000'),
        added_at=datetime(2026, 10, 1, 14, 0, tzinfo=dt_timezone.utc),
    )
    evening = FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('25.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 17, 0, tzinfo=dt_timezone.utc),
        reason='Damaged crates',
    )
    assert morning.pk != afternoon.pk != evening.pk
    assert FinishedGoodAddition.objects.filter(finished_good=finished_good).count() == 2
    assert FinishedGoodAdjustment.objects.filter(finished_good=finished_good).count() == 1
    quantities = list(
        FinishedGoodAddition.objects.filter(finished_good=finished_good)
        .order_by('added_at')
        .values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('500.000'), Decimal('300.000')]
    assert evening.quantity == Decimal('25.000')
    assert evening.adjustment_type == FinishedGoodAdjustmentType.DECREASE


@pytest.mark.django_db
def test_stock_record_uniqueness(warehouse, finished_good, fg_stock_record):
    duplicate = FinishedGoodStockRecord(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('20.000'),
        closing_quantity=Decimal('15.000'),
    )
    with pytest.raises(ValidationError):
        duplicate.save()

    later = FinishedGoodStockRecord.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 2),
        opening_quantity=Decimal('1575.000'),
        closing_quantity=Decimal('1400.000'),
    )
    assert fg_stock_record.pk != later.pk
    assert FinishedGoodStockRecord.objects.filter(
        warehouse=warehouse,
        finished_good=finished_good,
    ).count() == 2


@pytest.mark.django_db
def test_string_representations(
    warehouse, finished_good, fg_stock_record, production_output
):
    addition = FinishedGoodAddition.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('500.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        production_output=production_output,
    )
    increase = FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('10.000'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
        reason='Found crates',
    )
    decrease = FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('25.000'),
        adjustment_type=FinishedGoodAdjustmentType.DECREASE,
        occurred_at=datetime(2026, 10, 1, 17, 0, tzinfo=dt_timezone.utc),
        reason='Damaged crates',
    )
    reconciliation = FinishedGoodReconciliation.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        reconciliation_date=date(2026, 10, 1),
        notes='End of day count',
    )
    assert str(warehouse) == 'Main Factory — FG-MAIN'
    assert str(fg_stock_record) == 'FG-MAIN — CRATE-001 — 2026-10-01'
    assert str(addition) == 'FG-MAIN — CRATE-001 — 500.000'
    assert str(increase) == 'FG-MAIN — CRATE-001 — +10.000'
    assert str(decrease) == 'FG-MAIN — CRATE-001 — -25.000'
    assert str(reconciliation) == 'FG-MAIN — CRATE-001 — 2026-10-01'


@pytest.mark.django_db
def test_inactive_warehouse_rejection(warehouse, finished_good):
    warehouse.is_active = False
    warehouse.save()
    record = FinishedGoodStockRecord(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('8.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        record.save()
    assert 'warehouse' in extra_info.value.message_dict

    addition = FinishedGoodAddition(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        addition.save()
    assert 'warehouse' in extra_info.value.message_dict

    adjustment = FinishedGoodAdjustment(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('5.000'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=datetime(2026, 10, 1, 17, 0, tzinfo=dt_timezone.utc),
        reason='Count correction',
    )
    with pytest.raises(ValidationError) as extra_info:
        adjustment.save()
    assert 'warehouse' in extra_info.value.message_dict


@pytest.mark.django_db
def test_inactive_finished_good_stock_rejected(warehouse, finished_good):
    finished_good.is_active = False
    finished_good.save()
    record = FinishedGoodStockRecord(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('8.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        record.save()
    assert 'finished_good' in extra_info.value.message_dict


@pytest.mark.django_db
def test_finished_good_reconciliation_foundation(warehouse, finished_good):
    reconciliation = FinishedGoodReconciliation.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        reconciliation_date=date(2026, 10, 1),
        notes='End of day count review',
    )
    assert reconciliation.warehouse == warehouse
    assert reconciliation.finished_good == finished_good
    assert reconciliation.reconciliation_date == date(2026, 10, 1)
    assert reconciliation.notes == 'End of day count review'
    assert not hasattr(reconciliation, 'expected_quantity')
    assert not hasattr(reconciliation, 'variance')
    assert reconciliation.expected_closing_quantity is None
    assert reconciliation.actual_closing_quantity is None
    assert reconciliation.variance_quantity is None
    assert warehouse.reconciliations.count() == 1


@pytest.mark.django_db
def test_addition_production_output_factory_mismatch_rejected(
    warehouse, finished_good
):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_run = ProductionRun.objects.create(
        factory=other_factory,
        reference='PR-SOUTH-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    other_output = ProductionOutput.objects.create(
        production_run=other_run,
        output_name='South Crates',
        quantity=Decimal('100.000'),
        recorded_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    addition = FinishedGoodAddition(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        production_output=other_output,
    )
    with pytest.raises(ValidationError) as extra_info:
        addition.save()
    assert 'production_output' in extra_info.value.message_dict
