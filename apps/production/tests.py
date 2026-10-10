"""
Tests for Production App — M5 Production Runs & Output
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.factories.models import Factory
from apps.production.models import (
    FinishedGood,
    ProductionOutput,
    ProductionReject,
    ProductionRun,
    ProductionRunStatus,
)


@pytest.fixture
def production_run(db, factory):
    return ProductionRun.objects.create(
        factory=factory,
        reference='PR-20261001-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
        notes='Crate moulding run',
    )


@pytest.fixture
def production_output(db, production_run):
    return ProductionOutput.objects.create(
        production_run=production_run,
        output_name='Plastic Crates',
        quantity=Decimal('1200.000'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )


@pytest.mark.django_db
def test_production_run_creation(production_run, factory):
    assert production_run.factory == factory
    assert production_run.reference == 'PR-20261001-001'
    assert production_run.status == ProductionRunStatus.IN_PROGRESS
    assert production_run.started_at == datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc)
    assert production_run.ended_at is None
    assert production_run.notes == 'Crate moulding run'
    assert production_run.created_at is not None
    assert production_run.updated_at is not None
    assert factory.production_runs.count() == 1


@pytest.mark.django_db
def test_production_output_creation(production_output, production_run):
    assert production_output.production_run == production_run
    assert production_output.output_name == 'Plastic Crates'
    assert production_output.recorded_at == datetime(
        2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc
    )
    assert production_output.created_at is not None
    assert production_output.updated_at is not None
    assert production_run.outputs.count() == 1


@pytest.mark.django_db
def test_production_run_status_behaviour(factory):
    planned = ProductionRun.objects.create(
        factory=factory,
        reference='PR-20261001-010',
    )
    assert planned.status == ProductionRunStatus.PLANNED
    assert planned.started_at is None
    assert planned.ended_at is None

    planned.status = ProductionRunStatus.IN_PROGRESS
    planned.started_at = datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc)
    planned.save()
    planned.refresh_from_db()
    assert planned.status == ProductionRunStatus.IN_PROGRESS

    planned.status = ProductionRunStatus.COMPLETED
    planned.ended_at = datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc)
    planned.save()
    planned.refresh_from_db()
    assert planned.status == ProductionRunStatus.COMPLETED

    cancelled = ProductionRun.objects.create(
        factory=factory,
        reference='PR-20261001-011',
        status=ProductionRunStatus.CANCELLED,
    )
    assert cancelled.status == ProductionRunStatus.CANCELLED


@pytest.mark.django_db
def test_production_run_factory_association(production_run, factory):
    assert production_run.factory == factory
    assert production_run.factory.name == 'Main Factory'


@pytest.mark.django_db
def test_inactive_factory_production_run_rejected(factory):
    factory.is_active = False
    factory.save()
    run = ProductionRun(
        factory=factory,
        reference='PR-20261001-099',
    )
    with pytest.raises(ValidationError) as exc_info:
        run.save()
    assert 'factory' in exc_info.value.message_dict


@pytest.mark.django_db
def test_production_output_quantity_storage(production_output):
    assert production_output.quantity == Decimal('1200.000')
    assert isinstance(production_output.quantity, Decimal)


@pytest.mark.django_db
def test_production_output_decimal_quantity_behaviour(production_run):
    output = ProductionOutput.objects.create(
        production_run=production_run,
        output_name='Plastic Crates',
        quantity=Decimal('12.750'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    output.refresh_from_db()
    assert output.quantity == Decimal('12.750')
    assert output.quantity + Decimal('0.250') == Decimal('13.000')


@pytest.mark.django_db
def test_zero_quantity_production_output_rejected(production_run):
    output = ProductionOutput(
        production_run=production_run,
        output_name='Plastic Crates',
        quantity=Decimal('0.000'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        output.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_quantity_production_output_rejected(production_run):
    output = ProductionOutput(
        production_run=production_run,
        output_name='Plastic Crates',
        quantity=Decimal('-5.000'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        output.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_production_run_output_relationship(production_run):
    first = ProductionOutput.objects.create(
        production_run=production_run,
        output_name='Plastic Crates',
        quantity=Decimal('500.000'),
        recorded_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
    )
    second = ProductionOutput.objects.create(
        production_run=production_run,
        output_name='Plastic Crates',
        quantity=Decimal('700.000'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    assert first.production_run == production_run
    assert second.production_run == production_run
    assert production_run.outputs.count() == 2
    quantities = list(
        production_run.outputs.order_by('recorded_at').values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('500.000'), Decimal('700.000')]


@pytest.mark.django_db
def test_production_run_str(production_run):
    assert str(production_run) == 'Main Factory — PR-20261001-001'


@pytest.mark.django_db
def test_production_output_str(production_output):
    assert str(production_output) == 'PR-20261001-001 — Plastic Crates — 1200.000'


@pytest.mark.django_db
def test_ended_at_before_started_at_rejected(factory):
    run = ProductionRun(
        factory=factory,
        reference='PR-20261001-020',
        status=ProductionRunStatus.COMPLETED,
        started_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
        ended_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        run.save()
    assert 'ended_at' in exc_info.value.message_dict


@pytest.mark.django_db
def test_ended_at_without_started_at_rejected(factory):
    run = ProductionRun(
        factory=factory,
        reference='PR-20261001-021',
        ended_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        run.save()
    assert 'ended_at' in exc_info.value.message_dict


@pytest.mark.django_db
def test_completed_run_requires_started_and_ended_at(factory):
    run = ProductionRun(
        factory=factory,
        reference='PR-20261001-022',
        status=ProductionRunStatus.COMPLETED,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as exc_info:
        run.save()
    assert 'ended_at' in exc_info.value.message_dict


@pytest.mark.django_db
def test_in_progress_run_requires_started_at(factory):
    run = ProductionRun(
        factory=factory,
        reference='PR-20261001-023',
        status=ProductionRunStatus.IN_PROGRESS,
    )
    with pytest.raises(ValidationError) as exc_info:
        run.save()
    assert 'started_at' in exc_info.value.message_dict


@pytest.mark.django_db
def test_completed_run_with_valid_timestamps(factory):
    run = ProductionRun.objects.create(
        factory=factory,
        reference='PR-20261001-024',
        status=ProductionRunStatus.COMPLETED,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
        ended_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    assert run.ended_at > run.started_at


@pytest.mark.django_db
def test_duplicate_production_run_reference_rejected_per_factory(factory, production_run):
    duplicate = ProductionRun(
        factory=factory,
        reference='PR-20261001-001',
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_same_production_run_reference_allowed_across_factories(factory, production_run):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_run = ProductionRun.objects.create(
        factory=other_factory,
        reference='PR-20261001-001',
    )
    assert other_run.reference == production_run.reference
    assert other_run.factory != production_run.factory
    assert ProductionRun.objects.filter(reference='PR-20261001-001').count() == 2


@pytest.mark.django_db
def test_historical_production_runs_remain_separate(factory, production_run):
    later_run = ProductionRun.objects.create(
        factory=factory,
        reference='PR-20261001-002',
        status=ProductionRunStatus.COMPLETED,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
        ended_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    ProductionOutput.objects.create(
        production_run=production_run,
        output_name='Plastic Crates',
        quantity=Decimal('500.000'),
        recorded_at=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
    )
    ProductionOutput.objects.create(
        production_run=later_run,
        output_name='Plastic Crates',
        quantity=Decimal('700.000'),
        recorded_at=datetime(2026, 10, 2, 12, 0, tzinfo=dt_timezone.utc),
    )
    assert production_run.pk != later_run.pk
    assert ProductionRun.objects.filter(factory=factory).count() == 2
    assert production_run.outputs.get().quantity == Decimal('500.000')
    assert later_run.outputs.get().quantity == Decimal('700.000')


@pytest.fixture
def production_reject(db, production_run):
    return ProductionReject.objects.create(
        production_run=production_run,
        quantity=Decimal('12.000'),
        occurred_at=datetime(2026, 10, 1, 14, 0, tzinfo=dt_timezone.utc),
        reason='Misshapen crates',
    )


@pytest.mark.django_db
def test_production_reject_creation(production_reject, production_run):
    assert production_reject.production_run == production_run
    assert production_reject.quantity == Decimal('12.000')
    assert isinstance(production_reject.quantity, Decimal)
    assert production_reject.reason == 'Misshapen crates'
    assert production_run.rejects.count() == 1


@pytest.mark.django_db
def test_production_reject_decimal_quantity_behaviour(production_run):
    reject = ProductionReject.objects.create(
        production_run=production_run,
        quantity=Decimal('3.250'),
        occurred_at=datetime(2026, 10, 1, 14, 0, tzinfo=dt_timezone.utc),
        reason='Failed dimensions',
    )
    reject.refresh_from_db()
    assert reject.quantity == Decimal('3.250')
    assert reject.quantity + Decimal('0.750') == Decimal('4.000')


@pytest.mark.django_db
def test_zero_quantity_production_reject_rejected(production_run):
    reject = ProductionReject(
        production_run=production_run,
        quantity=Decimal('0.000'),
        occurred_at=datetime(2026, 10, 1, 14, 0, tzinfo=dt_timezone.utc),
        reason='Misshapen crates',
    )
    with pytest.raises(ValidationError) as exc_info:
        reject.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_negative_quantity_production_reject_rejected(production_run):
    reject = ProductionReject(
        production_run=production_run,
        quantity=Decimal('-4.000'),
        occurred_at=datetime(2026, 10, 1, 14, 0, tzinfo=dt_timezone.utc),
        reason='Misshapen crates',
    )
    with pytest.raises(ValidationError) as exc_info:
        reject.save()
    assert 'quantity' in exc_info.value.message_dict


@pytest.mark.django_db
def test_production_reject_linked_to_run(production_reject, production_run):
    assert production_reject.production_run_id == production_run.pk
    assert production_run.rejects.first() == production_reject


@pytest.mark.django_db
def test_historical_production_rejects_remain_separate(production_run):
    ProductionReject.objects.create(
        production_run=production_run,
        quantity=Decimal('5.000'),
        occurred_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
        reason='Misshapen crates',
    )
    ProductionReject.objects.create(
        production_run=production_run,
        quantity=Decimal('7.000'),
        occurred_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
        reason='Failed dimensions',
    )
    quantities = list(
        production_run.rejects.order_by('occurred_at').values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('5.000'), Decimal('7.000')]


@pytest.mark.django_db
def test_production_reject_str(production_reject):
    assert str(production_reject) == 'PR-20261001-001 — 12.000 — Misshapen crates'


@pytest.mark.django_db
def test_inactive_factory_production_reject_rejected(factory, production_run):
    factory.is_active = False
    factory.save()
    reject = ProductionReject(
        production_run=production_run,
        quantity=Decimal('12.000'),
        occurred_at=datetime(2026, 10, 1, 14, 0, tzinfo=dt_timezone.utc),
        reason='Misshapen crates',
    )
    with pytest.raises(ValidationError) as exc_info:
        reject.save()
    assert 'production_run' in exc_info.value.message_dict


@pytest.fixture
def finished_good(db, factory):
    return FinishedGood.objects.create(
        factory=factory,
        code='CRATE-001',
        name='Plastic Crates',
        description='Injection-moulded crates',
    )


@pytest.mark.django_db
def test_finished_good_creation(finished_good, factory):
    assert finished_good.factory == factory
    assert finished_good.code == 'CRATE-001'
    assert finished_good.name == 'Plastic Crates'
    assert finished_good.description == 'Injection-moulded crates'
    assert finished_good.is_active is True
    assert finished_good.created_at is not None
    assert factory.finished_goods.count() == 1


@pytest.mark.django_db
def test_finished_good_code_unique_per_factory(factory, finished_good):
    duplicate = FinishedGood(
        factory=factory,
        code='CRATE-001',
        name='Duplicate Crate',
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_same_finished_good_code_allowed_across_factories(factory, finished_good):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other = FinishedGood.objects.create(
        factory=other_factory,
        code='CRATE-001',
        name='Plastic Crates',
    )
    assert other.code == finished_good.code
    assert other.factory != finished_good.factory
    assert FinishedGood.objects.filter(code='CRATE-001').count() == 2


@pytest.mark.django_db
def test_inactive_factory_finished_good_rejected(factory):
    factory.is_active = False
    factory.save()
    item = FinishedGood(
        factory=factory,
        code='CRATE-099',
        name='Plastic Crates',
    )
    with pytest.raises(ValidationError) as extra_info:
        item.save()
    assert 'factory' in extra_info.value.message_dict


@pytest.mark.django_db
def test_finished_good_str(finished_good):
    assert str(finished_good) == 'CRATE-001 — Plastic Crates'


@pytest.mark.django_db
def test_production_output_linked_to_finished_good(production_run, finished_good):
    output = ProductionOutput.objects.create(
        production_run=production_run,
        output_name='Plastic Crates',
        finished_good=finished_good,
        quantity=Decimal('1200.000'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    assert output.finished_good == finished_good
    assert finished_good.outputs.count() == 1
    assert output.output_name == 'Plastic Crates'


@pytest.mark.django_db
def test_production_output_name_still_valid_without_finished_good(production_output):
    assert production_output.finished_good_id is None
    assert production_output.output_name == 'Plastic Crates'
    assert str(production_output) == 'PR-20261001-001 — Plastic Crates — 1200.000'


@pytest.mark.django_db
def test_production_output_finished_good_factory_mismatch_rejected(production_run):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_good = FinishedGood.objects.create(
        factory=other_factory,
        code='CRATE-SOUTH',
        name='South Crates',
    )
    output = ProductionOutput(
        production_run=production_run,
        output_name='Plastic Crates',
        finished_good=other_good,
        quantity=Decimal('100.000'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError) as extra_info:
        output.save()
    assert 'finished_good' in extra_info.value.message_dict


@pytest.mark.django_db
def test_production_output_requires_name_or_finished_good(production_run):
    output = ProductionOutput(
        production_run=production_run,
        quantity=Decimal('100.000'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )
    with pytest.raises(ValidationError):
        output.save()
