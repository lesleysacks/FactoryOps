"""
Tests for Materials App — M1–M4, M6 Waste/Scrap, M7 Reconciliation
"""

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.factories.models import Factory
from apps.materials.models import (
    Material,
    MaterialAddition,
    MaterialBatch,
    MaterialCategory,
    MaterialConsumption,
    MaterialScrap,
    MaterialWaste,
    StockReconciliation,
    StockRecord,
    UnitOfMeasure,
)
from apps.production.models import ProductionRun, ProductionRunStatus


@pytest.fixture
def unit_of_measure(db):
    return UnitOfMeasure.objects.create(name='Kilogram', symbol='kg')


@pytest.fixture
def material_category(db, factory):
    return MaterialCategory.objects.create(
        factory=factory,
        name='Raw Materials',
        description='Primary raw inputs',
    )


@pytest.fixture
def material(db, factory, material_category, unit_of_measure):
    return Material.objects.create(
        factory=factory,
        name='SAP',
        code='SAP-001',
        category=material_category,
        unit=unit_of_measure,
        minimum_stock_threshold=Decimal('10.000'),
        target_stock=Decimal('100.000'),
        notes='Super absorbent polymer',
    )


@pytest.mark.django_db
def test_unit_of_measure_creation(unit_of_measure):
    assert unit_of_measure.name == 'Kilogram'
    assert unit_of_measure.symbol == 'kg'
    assert unit_of_measure.is_active is True
    assert str(unit_of_measure) == 'Kilogram (kg)'


@pytest.mark.django_db
def test_material_category_creation(material_category, factory):
    assert material_category.factory == factory
    assert material_category.name == 'Raw Materials'
    assert material_category.is_active is True
    assert str(material_category) == 'Main Factory — Raw Materials'
    assert factory.material_categories.count() == 1


@pytest.mark.django_db
def test_material_creation(material, factory, material_category, unit_of_measure):
    assert material.factory == factory
    assert material.name == 'SAP'
    assert material.code == 'SAP-001'
    assert material.category == material_category
    assert material.unit == unit_of_measure
    assert material.minimum_stock_threshold == Decimal('10.000')
    assert material.target_stock == Decimal('100.000')
    assert material.is_active is True
    assert material.notes == 'Super absorbent polymer'
    assert str(material) == 'SAP-001 — SAP'
    assert factory.materials.count() == 1


@pytest.mark.django_db
def test_duplicate_material_code_rejected_per_factory(
    factory, material_category, unit_of_measure, material
):
    duplicate = Material(
        factory=factory,
        name='SAP Duplicate',
        code='SAP-001',
        category=material_category,
        unit=unit_of_measure,
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_same_material_code_allowed_across_factories(
    factory, material_category, unit_of_measure, material
):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_category = MaterialCategory.objects.create(
        factory=other_factory,
        name='Raw Materials',
    )
    other_material = Material.objects.create(
        factory=other_factory,
        name='SAP',
        code='SAP-001',
        category=other_category,
        unit=unit_of_measure,
    )
    assert other_material.code == material.code
    assert other_material.factory != material.factory
    assert Material.objects.filter(code='SAP-001').count() == 2


@pytest.mark.django_db
def test_negative_minimum_stock_threshold_rejected(
    factory, material_category, unit_of_measure
):
    material = Material(
        factory=factory,
        name='Glue',
        code='GLUE-001',
        category=material_category,
        unit=unit_of_measure,
        minimum_stock_threshold=Decimal('-1.000'),
    )
    with pytest.raises(ValidationError) as exc_info:
        material.save()
    assert 'minimum_stock_threshold' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_target_stock_rejected(
    factory, material_category, unit_of_measure
):
    material = Material(
        factory=factory,
        name='Glue',
        code='GLUE-001',
        category=material_category,
        unit=unit_of_measure,
        target_stock=Decimal('-5.000'),
    )
    with pytest.raises(ValidationError) as exc_info:
        material.save()
    assert 'target_stock' in exc_info.value.message_dict


@pytest.mark.django_db
def test_material_category_factory_mismatch_rejected(
    factory, unit_of_measure
):
    other_factory = Factory.objects.create(name='East Plant')
    other_category = MaterialCategory.objects.create(
        factory=other_factory,
        name='Consumables',
    )
    material = Material(
        factory=factory,
        name='Blue Tape',
        code='TAPE-001',
        category=other_category,
        unit=unit_of_measure,
    )
    with pytest.raises(ValidationError) as exc_info:
        material.save()
    assert 'category' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_material(material):
    material.is_active = False
    material.save()
    material.refresh_from_db()
    assert material.is_active is False


@pytest.mark.django_db
def test_duplicate_category_name_rejected_per_factory(factory):
    MaterialCategory.objects.create(factory=factory, name='Packaging')
    duplicate = MaterialCategory(factory=factory, name='Packaging')
    with pytest.raises(IntegrityError):
        duplicate.save()


@pytest.fixture
def stock_record(db, factory, material):
    return StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('50.000'),
        closing_quantity=Decimal('42.500'),
    )


@pytest.mark.django_db
def test_stock_record_creation(stock_record, factory, material):
    assert stock_record.factory == factory
    assert stock_record.material == material
    assert stock_record.recording_date == date(2026, 9, 19)
    assert stock_record.created_at is not None
    assert stock_record.updated_at is not None
    assert factory.stock_records.count() == 1
    assert material.stock_records.count() == 1


@pytest.mark.django_db
def test_opening_quantity_storage(stock_record):
    assert stock_record.opening_quantity == Decimal('50.000')


@pytest.mark.django_db
def test_closing_quantity_storage(stock_record):
    assert stock_record.closing_quantity == Decimal('42.500')


@pytest.mark.django_db
def test_negative_opening_quantity_rejected(factory, material):
    record = StockRecord(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('-1.000'),
        closing_quantity=Decimal('10.000'),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'opening_quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_closing_quantity_rejected(factory, material):
    record = StockRecord(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('-5.000'),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'closing_quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_factory_material_mismatch_rejected(factory, material):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    record = StockRecord(
        factory=other_factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('8.000'),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_duplicate_stock_record_rejected_per_factory_material_date(
    factory, material, stock_record
):
    duplicate = StockRecord(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('20.000'),
        closing_quantity=Decimal('15.000'),
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_historical_stock_records_remain_distinct_by_date(factory, material, stock_record):
    later_record = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 20),
        opening_quantity=Decimal('42.500'),
        closing_quantity=Decimal('30.000'),
    )
    assert stock_record.pk != later_record.pk
    assert StockRecord.objects.filter(factory=factory, material=material).count() == 2
    assert (
        StockRecord.objects.get(
            factory=factory,
            material=material,
            recording_date=date(2026, 9, 19),
        ).opening_quantity
        == Decimal('50.000')
    )
    assert (
        StockRecord.objects.get(
            factory=factory,
            material=material,
            recording_date=date(2026, 9, 20),
        ).opening_quantity
        == Decimal('42.500')
    )


@pytest.mark.django_db
def test_stock_record_str(stock_record):
    assert str(stock_record) == 'Main Factory — SAP-001 — 2026-09-19'


@pytest.mark.django_db
def test_opening_stock_can_be_recorded_without_closing(factory, material):
    record = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('50.000'),
    )
    assert record.opening_quantity == Decimal('50.000')
    assert record.closing_quantity is None


@pytest.mark.django_db
def test_closing_quantity_can_be_added_to_existing_record(factory, material):
    record = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('50.000'),
    )
    record.closing_quantity = Decimal('42.500')
    record.save()
    record.refresh_from_db()
    assert record.opening_quantity == Decimal('50.000')
    assert record.closing_quantity == Decimal('42.500')
    assert StockRecord.objects.filter(factory=factory, material=material).count() == 1


@pytest.mark.django_db
def test_zero_quantities_allowed(factory, material):
    record = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('0.000'),
        closing_quantity=Decimal('0.000'),
    )
    assert record.opening_quantity == Decimal('0.000')
    assert record.closing_quantity == Decimal('0.000')


@pytest.mark.django_db
def test_inactive_material_stock_record_rejected(factory, material):
    material.is_active = False
    material.save()
    record = StockRecord(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('8.000'),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_factory_stock_record_rejected(factory, material):
    factory.is_active = False
    factory.save()
    record = StockRecord(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('8.000'),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'factory' in exc_info.value.message_dict


@pytest.mark.django_db
def test_same_material_code_stock_records_allowed_across_factories(
    factory, material, material_category, unit_of_measure
):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_category = MaterialCategory.objects.create(
        factory=other_factory,
        name='Raw Materials',
    )
    other_material = Material.objects.create(
        factory=other_factory,
        name='SAP',
        code='SAP-001',
        category=other_category,
        unit=unit_of_measure,
    )
    first = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('50.000'),
        closing_quantity=Decimal('42.500'),
    )
    second = StockRecord.objects.create(
        factory=other_factory,
        material=other_material,
        recording_date=date(2026, 9, 19),
        opening_quantity=Decimal('12.000'),
        closing_quantity=Decimal('10.000'),
    )
    assert first.recording_date == second.recording_date
    assert first.factory != second.factory
    assert StockRecord.objects.filter(recording_date=date(2026, 9, 19)).count() == 2


@pytest.fixture
def material_batch(db, material):
    return MaterialBatch.objects.create(
        material=material,
        lot_number='SAP-20260919-01',
    )


@pytest.fixture
def material_addition(db, factory, material, material_batch):
    return MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('500.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )


@pytest.mark.django_db
def test_material_addition_creation(material_addition, factory, material, material_batch):
    assert material_addition.factory == factory
    assert material_addition.material == material
    assert material_addition.batch == material_batch
    assert material_addition.added_at == datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc)
    assert material_addition.created_at is not None
    assert material_addition.updated_at is not None
    assert factory.material_additions.count() == 1
    assert material.additions.count() == 1
    assert material_batch.additions.count() == 1


@pytest.mark.django_db
def test_material_addition_quantity_storage(material_addition):
    assert material_addition.quantity == Decimal('500.000')
    assert isinstance(material_addition.quantity, Decimal)


@pytest.mark.django_db
def test_material_addition_decimal_quantity_behavior(factory, material, material_batch):
    addition = MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('12.750'),
        added_at=datetime(2026, 9, 19, 13, 0, tzinfo=dt_timezone.utc),
    )
    addition.refresh_from_db()
    assert addition.quantity == Decimal('12.750')
    assert addition.quantity + Decimal('0.250') == Decimal('13.000')


@pytest.mark.django_db
def test_zero_quantity_addition_rejected(factory, material, material_batch):
    addition = MaterialAddition(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('0.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        addition.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_quantity_addition_rejected(factory, material, material_batch):
    addition = MaterialAddition(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('-10.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        addition.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_addition_factory_material_mismatch_rejected(factory, material, material_batch):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    addition = MaterialAddition(
        factory=other_factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('100.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        addition.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_historical_additions_remain_separate(factory, material, material_batch):
    first = MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('500.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    second = MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('300.000'),
        added_at=datetime(2026, 9, 19, 13, 0, tzinfo=dt_timezone.utc),
    )
    third = MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('200.000'),
        added_at=datetime(2026, 9, 19, 17, 0, tzinfo=dt_timezone.utc),
    )
    assert first.pk != second.pk != third.pk
    assert MaterialAddition.objects.filter(material=material).count() == 3
    assert MaterialAddition.objects.filter(batch=material_batch).count() == 3
    quantities = list(
        MaterialAddition.objects.filter(material=material)
        .order_by('added_at')
        .values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('500.000'), Decimal('300.000'), Decimal('200.000')]


@pytest.mark.django_db
def test_batch_lot_information_stored(material_batch, material_addition):
    assert material_batch.lot_number == 'SAP-20260919-01'
    assert material_batch.material == material_addition.material
    assert material_addition.batch.lot_number == 'SAP-20260919-01'
    assert str(material_batch) == 'SAP-001 — SAP-20260919-01'


@pytest.mark.django_db
def test_duplicate_lot_number_rejected_per_material(material, material_batch):
    duplicate = MaterialBatch(
        material=material,
        lot_number='SAP-20260919-01',
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_same_lot_number_allowed_across_materials(
    factory, material, material_batch, material_category, unit_of_measure
):
    other_material = Material.objects.create(
        factory=factory,
        name='Polypropylene',
        code='PP-001',
        category=material_category,
        unit=unit_of_measure,
    )
    other_batch = MaterialBatch.objects.create(
        material=other_material,
        lot_number='SAP-20260919-01',
    )
    assert other_batch.lot_number == material_batch.lot_number
    assert other_batch.material != material_batch.material
    assert MaterialBatch.objects.filter(lot_number='SAP-20260919-01').count() == 2


@pytest.mark.django_db
def test_same_lot_number_allowed_across_factories(
    factory, material, material_batch, unit_of_measure
):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_category = MaterialCategory.objects.create(
        factory=other_factory,
        name='Raw Materials',
    )
    other_material = Material.objects.create(
        factory=other_factory,
        name='SAP',
        code='SAP-001',
        category=other_category,
        unit=unit_of_measure,
    )
    other_batch = MaterialBatch.objects.create(
        material=other_material,
        lot_number='SAP-20260919-01',
    )
    assert other_batch.lot_number == material_batch.lot_number
    assert other_batch.material.factory != material_batch.material.factory
    assert MaterialBatch.objects.filter(lot_number='SAP-20260919-01').count() == 2


@pytest.mark.django_db
def test_multiple_additions_can_reference_same_batch(factory, material, material_batch):
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('500.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('300.000'),
        added_at=datetime(2026, 9, 19, 13, 0, tzinfo=dt_timezone.utc),
    )
    assert material_batch.additions.count() == 2


@pytest.mark.django_db
def test_addition_batch_material_mismatch_rejected(
    factory, material, material_category, unit_of_measure
):
    other_material = Material.objects.create(
        factory=factory,
        name='Polypropylene',
        code='PP-001',
        category=material_category,
        unit=unit_of_measure,
    )
    other_batch = MaterialBatch.objects.create(
        material=other_material,
        lot_number='PP-20260919-01',
    )
    addition = MaterialAddition(
        factory=factory,
        material=material,
        batch=other_batch,
        quantity=Decimal('100.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        addition.save()
    assert 'batch' in exc_info.value.message_dict


@pytest.mark.django_db
def test_material_addition_str(material_addition):
    assert str(material_addition) == 'Main Factory — SAP-001 — 500.000 — SAP-20260919-01'


@pytest.mark.django_db
def test_inactive_material_addition_rejected(factory, material, material_batch):
    material.is_active = False
    material.save()
    addition = MaterialAddition(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('100.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        addition.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_factory_addition_rejected(factory, material, material_batch):
    factory.is_active = False
    factory.save()
    addition = MaterialAddition(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('100.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        addition.save()
    assert 'factory' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_material_batch_rejected(material):
    material.is_active = False
    material.save()
    batch = MaterialBatch(
        material=material,
        lot_number='SAP-20260919-99',
    )
    with pytest.raises(ValidationError) as exc_info:
        batch.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_additions_do_not_overwrite_stock_records(factory, material, material_batch, stock_record):
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('500.000'),
        added_at=datetime(2026, 9, 19, 9, 0, tzinfo=dt_timezone.utc),
    )
    stock_record.refresh_from_db()
    assert stock_record.opening_quantity == Decimal('50.000')
    assert stock_record.closing_quantity == Decimal('42.500')
    assert StockRecord.objects.filter(factory=factory, material=material).count() == 1


@pytest.fixture
def material_consumption(db, factory, material):
    return MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('250.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
        production_reference='LINE-1-SHIFT-A',
    )


@pytest.mark.django_db
def test_material_consumption_creation(material_consumption, factory, material):
    assert material_consumption.factory == factory
    assert material_consumption.material == material
    assert material_consumption.consumed_at == datetime(
        2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc
    )
    assert material_consumption.created_at is not None
    assert material_consumption.updated_at is not None
    assert factory.material_consumptions.count() == 1
    assert material.consumptions.count() == 1


@pytest.mark.django_db
def test_material_consumption_quantity_storage(material_consumption):
    assert material_consumption.quantity == Decimal('250.000')
    assert isinstance(material_consumption.quantity, Decimal)


@pytest.mark.django_db
def test_material_consumption_decimal_quantity_behavior(factory, material):
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('0.500'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    consumption.refresh_from_db()
    assert consumption.quantity == Decimal('0.500')
    assert consumption.quantity + Decimal('0.250') == Decimal('0.750')


@pytest.mark.django_db
def test_zero_quantity_consumption_rejected(factory, material):
    consumption = MaterialConsumption(
        factory=factory,
        material=material,
        quantity=Decimal('0.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        consumption.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_quantity_consumption_rejected(factory, material):
    consumption = MaterialConsumption(
        factory=factory,
        material=material,
        quantity=Decimal('-5.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        consumption.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_consumption_factory_material_mismatch_rejected(factory, material):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    consumption = MaterialConsumption(
        factory=other_factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        consumption.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_historical_consumptions_remain_separate(factory, material):
    first = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('100.000'),
        consumed_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    second = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('250.000'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    third = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('75.000'),
        consumed_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
    )
    assert first.pk != second.pk
    assert second.pk != third.pk
    assert first.pk != third.pk
    assert MaterialConsumption.objects.filter(material=material).count() == 3
    quantities = list(
        MaterialConsumption.objects.filter(material=material)
        .order_by('consumed_at')
        .values_list('quantity', flat=True)
    )
    assert quantities == [
        Decimal('100.000'),
        Decimal('250.000'),
        Decimal('75.000'),
    ]


@pytest.mark.django_db
def test_material_consumption_str(material_consumption):
    assert (
        str(material_consumption)
        == 'Main Factory — SAP-001 — 250.000 — LINE-1-SHIFT-A'
    )


@pytest.mark.django_db
def test_material_consumption_str_without_production_reference(factory, material):
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    assert str(consumption) == 'Main Factory — SAP-001 — 25.000'


@pytest.mark.django_db
def test_inactive_material_consumption_rejected(factory, material):
    material.is_active = False
    material.save()
    consumption = MaterialConsumption(
        factory=factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        consumption.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_factory_consumption_rejected(factory, material):
    factory.is_active = False
    factory.save()
    consumption = MaterialConsumption(
        factory=factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        consumption.save()
    assert 'factory' in exc_info.value.message_dict


@pytest.mark.django_db
def test_optional_production_reference_stored(material_consumption):
    assert material_consumption.production_reference == 'LINE-1-SHIFT-A'


@pytest.mark.django_db
def test_production_reference_may_be_blank(factory, material):
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    assert consumption.production_reference == ''


@pytest.mark.django_db
def test_consumption_does_not_modify_stock_record(factory, material, stock_record):
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('10.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    stock_record.refresh_from_db()
    assert stock_record.opening_quantity == Decimal('50.000')
    assert stock_record.closing_quantity == Decimal('42.500')
    assert StockRecord.objects.filter(factory=factory, material=material).count() == 1


@pytest.mark.django_db
def test_consumption_does_not_modify_material_addition(
    factory, material, material_batch, material_addition
):
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('10.000'),
        consumed_at=datetime(2026, 10, 1, 8, 30, tzinfo=dt_timezone.utc),
    )
    material_addition.refresh_from_db()
    assert material_addition.quantity == Decimal('500.000')
    assert MaterialAddition.objects.filter(material=material).count() == 1


@pytest.fixture
def material_waste(db, factory, material):
    return MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )


@pytest.fixture
def material_scrap(db, factory, material):
    return MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('8.000'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )


@pytest.fixture
def stock_reconciliation(db, factory, material):
    return StockReconciliation.objects.create(
        factory=factory,
        material=material,
        reconciliation_date=date(2026, 10, 1),
        notes='End of day count review',
    )


@pytest.mark.django_db
def test_material_waste_creation(material_waste, factory, material):
    assert material_waste.factory == factory
    assert material_waste.material == material
    assert material_waste.quantity == Decimal('5.000')
    assert isinstance(material_waste.quantity, Decimal)
    assert material_waste.reason == 'Spillage'
    assert material_waste.occurred_at == datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc)
    assert factory.material_wastes.count() == 1
    assert material.wastes.count() == 1


@pytest.mark.django_db
def test_material_scrap_creation(material_scrap, factory, material):
    assert material_scrap.factory == factory
    assert material_scrap.material == material
    assert material_scrap.quantity == Decimal('8.000')
    assert isinstance(material_scrap.quantity, Decimal)
    assert material_scrap.reason == 'Damaged bags'
    assert factory.material_scraps.count() == 1
    assert material.scraps.count() == 1


@pytest.mark.django_db
def test_waste_decimal_quantity_behaviour(factory, material):
    waste = MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('1.250'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Trim loss',
    )
    waste.refresh_from_db()
    assert waste.quantity == Decimal('1.250')
    assert waste.quantity + Decimal('0.750') == Decimal('2.000')


@pytest.mark.django_db
def test_scrap_decimal_quantity_behaviour(factory, material):
    scrap = MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('0.500'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Destroyed material',
    )
    scrap.refresh_from_db()
    assert scrap.quantity == Decimal('0.500')
    assert scrap.quantity + Decimal('0.500') == Decimal('1.000')


@pytest.mark.django_db
def test_zero_quantity_waste_rejected(factory, material):
    waste = MaterialWaste(
        factory=factory,
        material=material,
        quantity=Decimal('0.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    with pytest.raises(ValidationError) as exc_info:
        waste.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_zero_quantity_scrap_rejected(factory, material):
    scrap = MaterialScrap(
        factory=factory,
        material=material,
        quantity=Decimal('0.000'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    with pytest.raises(ValidationError) as exc_info:
        scrap.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_quantity_waste_rejected(factory, material):
    waste = MaterialWaste(
        factory=factory,
        material=material,
        quantity=Decimal('-1.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    with pytest.raises(ValidationError) as exc_info:
        waste.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_quantity_scrap_rejected(factory, material):
    scrap = MaterialScrap(
        factory=factory,
        material=material,
        quantity=Decimal('-2.000'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    with pytest.raises(ValidationError) as exc_info:
        scrap.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_waste_factory_material_mismatch_rejected(factory, material):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    waste = MaterialWaste(
        factory=other_factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    with pytest.raises(ValidationError) as exc_info:
        waste.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_scrap_factory_material_mismatch_rejected(factory, material):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    scrap = MaterialScrap(
        factory=other_factory,
        material=material,
        quantity=Decimal('8.000'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    with pytest.raises(ValidationError) as exc_info:
        scrap.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_historical_waste_events_remain_separate(factory, material):
    first = MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    second = MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('2.000'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Evaporation',
    )
    third = MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('1.000'),
        occurred_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
        reason='Trim loss',
    )
    assert first.pk != second.pk != third.pk
    quantities = list(
        MaterialWaste.objects.filter(material=material)
        .order_by('occurred_at')
        .values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('5.000'), Decimal('2.000'), Decimal('1.000')]


@pytest.mark.django_db
def test_historical_scrap_events_remain_separate(factory, material):
    MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('3.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('4.000'),
        occurred_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
        reason='Destroyed material',
    )
    assert MaterialScrap.objects.filter(material=material).count() == 2


@pytest.mark.django_db
def test_material_waste_str(material_waste):
    assert str(material_waste) == 'Main Factory — SAP-001 — 5.000 — Spillage'


@pytest.mark.django_db
def test_material_scrap_str(material_scrap):
    assert str(material_scrap) == 'Main Factory — SAP-001 — 8.000 — Damaged bags'


@pytest.mark.django_db
def test_inactive_material_waste_rejected(factory, material):
    material.is_active = False
    material.save()
    waste = MaterialWaste(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    with pytest.raises(ValidationError) as exc_info:
        waste.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_factory_waste_rejected(factory, material):
    factory.is_active = False
    factory.save()
    waste = MaterialWaste(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    with pytest.raises(ValidationError) as exc_info:
        waste.save()
    assert 'factory' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_material_scrap_rejected(factory, material):
    material.is_active = False
    material.save()
    scrap = MaterialScrap(
        factory=factory,
        material=material,
        quantity=Decimal('8.000'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    with pytest.raises(ValidationError) as exc_info:
        scrap.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_factory_scrap_rejected(factory, material):
    factory.is_active = False
    factory.save()
    scrap = MaterialScrap(
        factory=factory,
        material=material,
        quantity=Decimal('8.000'),
        occurred_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    with pytest.raises(ValidationError) as exc_info:
        scrap.save()
    assert 'factory' in exc_info.value.message_dict


@pytest.mark.django_db
def test_stock_reconciliation_creation(stock_reconciliation, factory, material):
    assert stock_reconciliation.factory == factory
    assert stock_reconciliation.material == material
    assert stock_reconciliation.reconciliation_date == date(2026, 10, 1)
    assert stock_reconciliation.notes == 'End of day count review'
    assert not hasattr(stock_reconciliation, 'expected_quantity')
    assert not hasattr(stock_reconciliation, 'variance')
    assert factory.stock_reconciliations.count() == 1


@pytest.mark.django_db
def test_stock_reconciliation_str(stock_reconciliation):
    assert str(stock_reconciliation) == 'Main Factory — SAP-001 — 2026-10-01'


@pytest.mark.django_db
def test_stock_reconciliation_factory_material_mismatch_rejected(factory, material):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    record = StockReconciliation(
        factory=other_factory,
        material=material,
        reconciliation_date=date(2026, 10, 1),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_duplicate_stock_reconciliation_rejected(factory, material, stock_reconciliation):
    duplicate = StockReconciliation(
        factory=factory,
        material=material,
        reconciliation_date=date(2026, 10, 1),
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_historical_stock_reconciliations_remain_separate(
    factory, material, stock_reconciliation
):
    later = StockReconciliation.objects.create(
        factory=factory,
        material=material,
        reconciliation_date=date(2026, 10, 2),
    )
    assert stock_reconciliation.pk != later.pk
    assert StockReconciliation.objects.filter(material=material).count() == 2


@pytest.mark.django_db
def test_inactive_material_reconciliation_rejected(factory, material):
    material.is_active = False
    material.save()
    record = StockReconciliation(
        factory=factory,
        material=material,
        reconciliation_date=date(2026, 10, 1),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'material' in exc_info.value.message_dict


@pytest.mark.django_db
def test_inactive_factory_reconciliation_rejected(factory, material):
    factory.is_active = False
    factory.save()
    record = StockReconciliation(
        factory=factory,
        material=material,
        reconciliation_date=date(2026, 10, 1),
    )
    with pytest.raises(ValidationError) as exc_info:
        record.save()
    assert 'factory' in exc_info.value.message_dict


@pytest.mark.django_db
def test_waste_does_not_modify_stock_record(factory, material, stock_record):
    MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    stock_record.refresh_from_db()
    assert stock_record.opening_quantity == Decimal('50.000')
    assert stock_record.closing_quantity == Decimal('42.500')


@pytest.fixture
def reconciliation_stock_record(db, factory, material):
    return StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('100.000'),
        closing_quantity=Decimal('110.000'),
    )


@pytest.mark.django_db
def test_expected_closing_calculation(
    factory, material, material_batch, stock_reconciliation, reconciliation_stock_record
):
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('20.000'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('3.000'),
        occurred_at=datetime(2026, 10, 1, 13, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    stock_reconciliation.calculate()
    stock_reconciliation.refresh_from_db()
    assert stock_reconciliation.expected_closing_quantity == Decimal('122.000')
    assert stock_reconciliation.calculated_at is not None


@pytest.mark.django_db
def test_variance_calculation(
    factory, material, material_batch, stock_reconciliation, reconciliation_stock_record
):
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('20.000'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('3.000'),
        occurred_at=datetime(2026, 10, 1, 13, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    stock_reconciliation.calculate()
    stock_reconciliation.refresh_from_db()
    assert stock_reconciliation.actual_closing_quantity == Decimal('110.000')
    assert stock_reconciliation.expected_closing_quantity == Decimal('122.000')
    assert stock_reconciliation.variance_quantity == Decimal('-12.000')


@pytest.mark.django_db
def test_reconciliation_includes_additions(
    factory, material, material_batch, stock_reconciliation, reconciliation_stock_record
):
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('25.500'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('125.500')


@pytest.mark.django_db
def test_reconciliation_includes_consumption(
    factory, material, stock_reconciliation, reconciliation_stock_record
):
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('40.000'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('60.000')


@pytest.mark.django_db
def test_reconciliation_includes_waste(
    factory, material, stock_reconciliation, reconciliation_stock_record
):
    MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('7.000'),
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Trim loss',
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('93.000')


@pytest.mark.django_db
def test_reconciliation_includes_scrap(
    factory, material, stock_reconciliation, reconciliation_stock_record
):
    MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('4.000'),
        occurred_at=datetime(2026, 10, 1, 13, 0, tzinfo=dt_timezone.utc),
        reason='Destroyed material',
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('96.000')


@pytest.mark.django_db
def test_reconciliation_excludes_unrelated_factory(
    factory, material, stock_reconciliation, reconciliation_stock_record,
    material_category, unit_of_measure
):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_category = MaterialCategory.objects.create(
        factory=other_factory,
        name='Raw Materials',
    )
    other_material = Material.objects.create(
        factory=other_factory,
        name='SAP',
        code='SAP-001',
        category=other_category,
        unit=unit_of_measure,
    )
    other_batch = MaterialBatch.objects.create(
        material=other_material,
        lot_number='SAP-OTHER-01',
    )
    MaterialAddition.objects.create(
        factory=other_factory,
        material=other_material,
        batch=other_batch,
        quantity=Decimal('999.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('100.000')


@pytest.mark.django_db
def test_reconciliation_excludes_unrelated_material(
    factory, material, material_category, unit_of_measure,
    stock_reconciliation, reconciliation_stock_record
):
    other_material = Material.objects.create(
        factory=factory,
        name='Polypropylene',
        code='PP-001',
        category=material_category,
        unit=unit_of_measure,
    )
    other_batch = MaterialBatch.objects.create(
        material=other_material,
        lot_number='PP-20261001-01',
    )
    MaterialAddition.objects.create(
        factory=factory,
        material=other_material,
        batch=other_batch,
        quantity=Decimal('999.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('100.000')


@pytest.mark.django_db
def test_reconciliation_excludes_events_on_other_dates(
    factory, material, material_batch, stock_reconciliation, reconciliation_stock_record
):
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 2, 9, 0, tzinfo=dt_timezone.utc),
    )
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('10.000'),
        consumed_at=datetime(2026, 9, 30, 11, 0, tzinfo=dt_timezone.utc),
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('100.000')


@pytest.mark.django_db
def test_reconciliation_decimal_calculation_accuracy(
    factory, material, material_batch, stock_reconciliation, reconciliation_stock_record
):
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('0.125'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('0.050'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('100.075')
    assert stock_reconciliation.variance_quantity == Decimal('9.925')


@pytest.mark.django_db
def test_reconciliation_does_not_alter_source_records(
    factory, material, material_batch, stock_reconciliation, reconciliation_stock_record
):
    addition = MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('50.000'),
        added_at=datetime(2026, 10, 1, 9, 0, tzinfo=dt_timezone.utc),
    )
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('20.000'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    waste = MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
        reason='Spillage',
    )
    scrap = MaterialScrap.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('3.000'),
        occurred_at=datetime(2026, 10, 1, 13, 0, tzinfo=dt_timezone.utc),
        reason='Damaged bags',
    )
    stock_reconciliation.calculate()
    reconciliation_stock_record.refresh_from_db()
    addition.refresh_from_db()
    consumption.refresh_from_db()
    waste.refresh_from_db()
    scrap.refresh_from_db()
    assert reconciliation_stock_record.opening_quantity == Decimal('100.000')
    assert reconciliation_stock_record.closing_quantity == Decimal('110.000')
    assert addition.quantity == Decimal('50.000')
    assert consumption.quantity == Decimal('20.000')
    assert waste.quantity == Decimal('5.000')
    assert scrap.quantity == Decimal('3.000')
    assert StockRecord.objects.filter(
        factory=factory, material=material, recording_date=date(2026, 10, 1)
    ).count() == 1


@pytest.mark.django_db
def test_reconciliation_requires_stock_record(stock_reconciliation):
    with pytest.raises(ValidationError) as exc_info:
        stock_reconciliation.calculate()
    assert 'reconciliation_date' in exc_info.value.message_dict


@pytest.mark.django_db
def test_reconciliation_without_closing_quantity(
    factory, material, stock_reconciliation
):
    StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('100.000'),
    )
    stock_reconciliation.calculate()
    stock_reconciliation.refresh_from_db()
    assert stock_reconciliation.expected_closing_quantity == Decimal('100.000')
    assert stock_reconciliation.actual_closing_quantity is None
    assert stock_reconciliation.variance_quantity is None


@pytest.mark.django_db
def test_positive_variance_when_actual_exceeds_expected(
    factory, material, stock_reconciliation, reconciliation_stock_record
):
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('10.000'),
        consumed_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
    )
    stock_reconciliation.calculate()
    assert stock_reconciliation.expected_closing_quantity == Decimal('90.000')
    assert stock_reconciliation.actual_closing_quantity == Decimal('110.000')
    assert stock_reconciliation.variance_quantity == Decimal('20.000')


@pytest.mark.django_db
def test_consumption_linked_to_production_run(factory, material):
    run = ProductionRun.objects.create(
        factory=factory,
        reference='PR-20261001-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        production_run=run,
        production_reference='LINE-1-SHIFT-A',
    )
    assert consumption.production_run == run
    assert run.material_consumptions.count() == 1
    assert consumption.production_reference == 'LINE-1-SHIFT-A'


@pytest.mark.django_db
def test_consumption_production_run_factory_mismatch_rejected(factory, material):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_run = ProductionRun.objects.create(
        factory=other_factory,
        reference='PR-20261001-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    consumption = MaterialConsumption(
        factory=factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
        production_run=other_run,
    )
    with pytest.raises(ValidationError) as exc_info:
        consumption.save()
    assert 'production_run' in exc_info.value.message_dict


@pytest.mark.django_db
def test_consumption_without_production_run_still_valid(factory, material):
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('25.000'),
        consumed_at=datetime(2026, 10, 1, 10, 0, tzinfo=dt_timezone.utc),
    )
    assert consumption.production_run_id is None
    assert consumption.production_reference == ''
