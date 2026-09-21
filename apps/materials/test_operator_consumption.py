"""
Tests for M4 operator material consumption.

Records MaterialConsumption against an explicit ProductionRun.
Does not mutate StockRecord or MaterialAddition.
Does not cover waste, QC, or reconciliation.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.factories.models import Factory, ProductionLine
from apps.machines.models import Machine, MachineStatus
from apps.materials.models import (
    Material,
    MaterialAddition,
    MaterialBatch,
    MaterialCategory,
    MaterialConsumption,
    StockRecord,
    UnitOfMeasure,
)
from apps.production.models import ProductionRun, ProductionRunStatus


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='cons_supervisor',
        email='cons-sup@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.fixture
def admin_user(db, factory):
    return User.objects.create_user(
        username='cons_admin',
        email='cons-admin@factoryops.local',
        password='Password123!',
        role=User.Role.ADMIN,
        factory=factory,
        is_staff=True,
    )


@pytest.fixture
def qc_user(db, factory):
    return User.objects.create_user(
        username='cons_qc',
        email='cons-qc@factoryops.local',
        password='Password123!',
        role=User.Role.QC,
        factory=factory,
    )


@pytest.fixture
def machine(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Press 1',
        code='MC-CONS-001',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def material_batch(db, material):
    return MaterialBatch.objects.create(
        material=material,
        lot_number='SAP-CONS-01',
    )


@pytest.fixture
def other_factory(db):
    return Factory.objects.create(name='South Plant', location='Building 2')


@pytest.fixture
def other_material(db, other_factory):
    category = MaterialCategory.objects.create(factory=other_factory, name='Raw Materials')
    unit = UnitOfMeasure.objects.create(name='Gram', symbol='g')
    return Material.objects.create(
        factory=other_factory,
        name='Resin',
        code='RES-CONS-001',
        category=category,
        unit=unit,
    )


@pytest.fixture
def other_batch(db, other_material):
    return MaterialBatch.objects.create(
        material=other_material,
        lot_number='RES-SOUTH-01',
    )


@pytest.fixture
def other_machine(db, other_factory):
    line = ProductionLine.objects.create(
        factory=other_factory,
        name='South Line',
        code='S1',
    )
    return Machine.objects.create(
        production_line=line,
        name='South Press',
        code='MC-CONS-SOUTH',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def second_material(db, factory, material_category, unit_of_measure):
    return Material.objects.create(
        factory=factory,
        name='Fibre',
        code='FIB-CONS-001',
        category=material_category,
        unit=unit_of_measure,
    )


@pytest.fixture
def second_batch(db, second_material):
    return MaterialBatch.objects.create(
        material=second_material,
        lot_number='FIB-CONS-01',
    )


def _start_run(client, machine):
    response = client.post(reverse('dashboard:machine_start', args=[machine.pk]))
    assert response.status_code == 302
    return ProductionRun.objects.get()


def _consume(client, run, material, batch, quantity='5.000', extra=None):
    data = {
        'material': material.pk,
        'batch': batch.pk,
        'quantity': quantity,
    }
    if extra:
        data.update(extra)
    return client.post(
        reverse('dashboard:production_consumption', args=[run.pk]),
        data,
    )


@pytest.mark.django_db
def test_consumption_capture_requires_authentication(client, machine):
    response = client.get(reverse('dashboard:production_consumption', args=[1]))
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_operator_can_access_consumption_capture(
    client, user, machine, material, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    response = client.get(
        reverse('dashboard:production_consumption', args=[run.pk]),
        {'material': material.pk},
    )
    assert response.status_code == 200
    assert b'Record consumption' in response.content
    assert run.reference.encode() in response.content
    assert b'SAP-CONS-01' in response.content
    assert b'Record material consumption' in response.content


@pytest.mark.django_db
def test_supervisor_can_access_consumption_capture(client, supervisor, machine):
    client.force_login(supervisor)
    run = _start_run(client, machine)
    response = client.get(reverse('dashboard:production_consumption', args=[run.pk]))
    assert response.status_code == 200
    assert b'Record consumption' in response.content


@pytest.mark.django_db
def test_admin_can_access_consumption_capture(client, admin_user, machine):
    client.force_login(admin_user)
    run = _start_run(client, machine)
    response = client.get(reverse('dashboard:production_consumption', args=[run.pk]))
    assert response.status_code == 200
    assert b'Record consumption' in response.content


@pytest.mark.django_db
def test_qc_cannot_record_consumption(
    client, qc_user, user, machine, material, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    client.force_login(qc_user)
    assert client.get(
        reverse('dashboard:production_consumption', args=[run.pk])
    ).status_code == 403
    assert _consume(client, run, material, material_batch).status_code == 403
    assert MaterialConsumption.objects.count() == 0


@pytest.mark.django_db
def test_foreign_production_run_rejected(
    client, user, other_machine, other_material, other_batch
):
    other_run = ProductionRun.objects.create(
        factory=other_machine.production_line.factory,
        production_line=other_machine.production_line,
        machine=other_machine,
        reference='PR-FOREIGN-CONS',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=timezone.now(),
    )
    client.force_login(user)
    assert client.get(
        reverse('dashboard:production_consumption', args=[other_run.pk])
    ).status_code == 404
    assert _consume(client, other_run, other_material, other_batch).status_code == 404
    assert MaterialConsumption.objects.count() == 0


@pytest.mark.django_db
def test_foreign_material_rejected(
    client, user, machine, other_material, other_batch, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    response = _consume(client, run, other_material, other_batch)
    assert response.status_code == 200
    assert MaterialConsumption.objects.count() == 0
    assert b'Select a valid choice' in response.content


@pytest.mark.django_db
def test_foreign_batch_rejected(
    client, user, machine, material, other_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    response = _consume(client, run, material, other_batch)
    assert response.status_code == 200
    assert MaterialConsumption.objects.count() == 0
    assert b'Select a valid choice' in response.content


@pytest.mark.django_db
def test_batch_from_wrong_material_rejected(
    client, user, machine, material, second_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    response = _consume(client, run, material, second_batch)
    assert response.status_code == 200
    assert MaterialConsumption.objects.count() == 0
    assert b'Select a valid choice' in response.content


@pytest.mark.django_db
def test_inactive_material_rejected(
    client, user, machine, material, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    material.is_active = False
    material.save()
    response = _consume(client, run, material, material_batch)
    assert response.status_code == 200
    assert MaterialConsumption.objects.count() == 0


@pytest.mark.django_db
def test_quantity_must_be_positive(client, user, machine, material, material_batch):
    client.force_login(user)
    run = _start_run(client, machine)
    url = reverse('dashboard:production_consumption', args=[run.pk])
    for quantity in ('0', '0.000', '-1', '-0.001'):
        response = client.post(url, {
            'material': material.pk,
            'batch': material_batch.pk,
            'quantity': quantity,
        })
        assert response.status_code == 200
        assert MaterialConsumption.objects.count() == 0


@pytest.mark.django_db
def test_valid_consumption_creates_event(
    client, user, machine, material, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    before = timezone.now()
    response = _consume(
        client,
        run,
        material,
        material_batch,
        '12.250',
        extra={
            'consumed_at': '2019-01-01 00:00:00',
            'recorded_by': 999,
            'factory': 999,
            'production_run': 999,
        },
    )
    assert response.status_code == 302
    assert response.url == reverse('dashboard:production_run', args=[run.pk])
    event = MaterialConsumption.objects.get()
    assert event.production_run_id == run.pk
    assert event.material_id == material.pk
    assert event.batch_id == material_batch.pk
    assert event.quantity == Decimal('12.250')
    assert event.factory_id == user.factory_id
    assert event.recorded_by_id == user.pk
    assert event.consumed_at is not None
    assert event.consumed_at >= before
    assert event.consumed_at.year != 2019


@pytest.mark.django_db
def test_completed_run_cannot_receive_operator_consumption(
    client, user, machine, material, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    client.post(reverse('dashboard:production_complete', args=[run.pk]))
    assert client.get(
        reverse('dashboard:production_consumption', args=[run.pk])
    ).status_code == 404
    assert _consume(client, run, material, material_batch).status_code == 404
    assert MaterialConsumption.objects.count() == 0


@pytest.mark.django_db
def test_consumption_appears_on_production_run_page(
    client, user, machine, material, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    empty = client.get(reverse('dashboard:production_run', args=[run.pk]))
    assert empty.status_code == 200
    assert b'No material consumption recorded on this run yet.' in empty.content
    _consume(client, run, material, material_batch, '3.000')
    page = client.get(reverse('dashboard:production_run', args=[run.pk]))
    assert b'SAP-001' in page.content
    assert b'SAP-CONS-01' in page.content
    assert b'3.000' in page.content
    assert user.username.encode() in page.content
    assert b'No material consumption recorded on this run yet.' not in page.content


@pytest.mark.django_db
def test_stock_record_not_modified_by_consumption(
    client, user, factory, machine, material, material_batch
):
    record = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=timezone.now().date(),
        opening_quantity=Decimal('100.000'),
        closing_quantity=Decimal('90.000'),
    )
    client.force_login(user)
    run = _start_run(client, machine)
    _consume(client, run, material, material_batch, '120.000')
    record.refresh_from_db()
    assert record.opening_quantity == Decimal('100.000')
    assert record.closing_quantity == Decimal('90.000')
    assert StockRecord.objects.filter(pk=record.pk).count() == 1
    assert MaterialConsumption.objects.get().quantity == Decimal('120.000')


@pytest.mark.django_db
def test_material_addition_not_modified_by_consumption(
    client, user, factory, machine, material, material_batch
):
    addition = MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('500.000'),
    )
    client.force_login(user)
    run = _start_run(client, machine)
    _consume(client, run, material, material_batch, '8.000')
    addition.refresh_from_db()
    assert addition.quantity == Decimal('500.000')
    assert MaterialAddition.objects.filter(pk=addition.pk).count() == 1


@pytest.mark.django_db
def test_multiple_consumption_events_same_batch_and_run(
    client, user, machine, material, material_batch
):
    client.force_login(user)
    run = _start_run(client, machine)
    _consume(client, run, material, material_batch, '2.000')
    _consume(client, run, material, material_batch, '4.500')
    events = list(MaterialConsumption.objects.order_by('quantity'))
    assert len(events) == 2
    assert events[0].batch_id == events[1].batch_id == material_batch.pk
    assert events[0].production_run_id == events[1].production_run_id == run.pk
    assert [event.quantity for event in events] == [
        Decimal('2.000'),
        Decimal('4.500'),
    ]
