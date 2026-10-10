"""
Tests for production-run material state snapshots.

Records ProductionRunMaterialState against an explicit ProductionRun.
Does not mutate StockRecord, MaterialAddition, or MaterialConsumption.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
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
from apps.production.models import (
    ProductionRun,
    ProductionRunMaterialState,
    ProductionRunStatus,
)


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='state_supervisor',
        email='state-sup@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.fixture
def admin_user(db, factory):
    return User.objects.create_user(
        username='state_admin',
        email='state-admin@factoryops.local',
        password='Password123!',
        role=User.Role.ADMIN,
        factory=factory,
        is_staff=True,
    )


@pytest.fixture
def qc_user(db, factory):
    return User.objects.create_user(
        username='state_qc',
        email='state-qc@factoryops.local',
        password='Password123!',
        role=User.Role.QC,
        factory=factory,
    )


@pytest.fixture
def machine(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Press 1',
        code='MC-STATE-001',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def second_material(db, factory, material_category, unit_of_measure):
    return Material.objects.create(
        factory=factory,
        name='Tissue',
        code='TIS-STATE-001',
        category=material_category,
        unit=unit_of_measure,
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
        code='RES-STATE-001',
        category=category,
        unit=unit,
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
        code='MC-STATE-SOUTH',
        status=MachineStatus.OPERATIONAL,
    )


def _start_run(client, machine):
    response = client.post(reverse('dashboard:machine_start', args=[machine.pk]))
    assert response.status_code == 302
    return ProductionRun.objects.filter(machine=machine).latest('pk')


def _record_state(client, run, material, roll='10.000', spare='2.000', extra=None):
    data = {
        'material': material.pk,
        'roll_quantity': roll,
        'spare_roll_quantity': spare,
    }
    if extra:
        data.update(extra)
    return client.post(
        reverse('dashboard:production_material_state', args=[run.pk]),
        data,
    )


@pytest.mark.django_db
def test_material_state_requires_authentication(client):
    response = client.get(reverse('dashboard:production_material_state', args=[1]))
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_operator_can_record_material_state(client, user, machine, material):
    client.force_login(user)
    run = _start_run(client, machine)
    before = timezone.now()
    response = _record_state(
        client,
        run,
        material,
        extra={'recorded_at': '2019-01-01 00:00:00', 'recorded_by': 999},
    )
    assert response.status_code == 302
    snapshot = ProductionRunMaterialState.objects.get()
    assert snapshot.production_run_id == run.pk
    assert snapshot.material_id == material.pk
    assert snapshot.roll_quantity == Decimal('10.000')
    assert snapshot.spare_roll_quantity == Decimal('2.000')
    assert snapshot.recorded_by_id == user.pk
    assert snapshot.recorded_at >= before
    assert snapshot.recorded_at.year != 2019


@pytest.mark.django_db
def test_supervisor_and_admin_can_access_material_state(
    client, supervisor, admin_user, machine, material
):
    client.force_login(supervisor)
    run = _start_run(client, machine)
    assert client.get(
        reverse('dashboard:production_material_state', args=[run.pk])
    ).status_code == 200
    client.force_login(admin_user)
    assert _record_state(client, run, material, '1.000', '0.000').status_code == 302
    assert ProductionRunMaterialState.objects.count() == 1


@pytest.mark.django_db
def test_qc_cannot_record_material_state(client, qc_user, user, machine, material):
    client.force_login(user)
    run = _start_run(client, machine)
    client.force_login(qc_user)
    assert client.get(
        reverse('dashboard:production_material_state', args=[run.pk])
    ).status_code == 403
    assert _record_state(client, run, material).status_code == 403
    assert ProductionRunMaterialState.objects.count() == 0


@pytest.mark.django_db
def test_foreign_run_and_material_rejected(
    client, user, machine, material, other_machine, other_material
):
    other_run = ProductionRun.objects.create(
        factory=other_machine.production_line.factory,
        production_line=other_machine.production_line,
        machine=other_machine,
        reference='PR-FOREIGN-STATE',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=timezone.now(),
    )
    client.force_login(user)
    assert client.get(
        reverse('dashboard:production_material_state', args=[other_run.pk])
    ).status_code == 404
    assert _record_state(client, other_run, other_material).status_code == 404
    run = _start_run(client, machine)
    response = _record_state(client, run, other_material)
    assert response.status_code == 200
    assert ProductionRunMaterialState.objects.count() == 0
    assert b'Select a valid choice' in response.content


@pytest.mark.django_db
def test_negative_quantities_rejected(client, user, machine, material):
    client.force_login(user)
    run = _start_run(client, machine)
    for roll, spare in (('-1', '0'), ('0', '-0.001')):
        response = _record_state(client, run, material, roll, spare)
        assert response.status_code == 200
        assert ProductionRunMaterialState.objects.count() == 0


@pytest.mark.django_db
def test_zero_quantities_allowed(client, user, machine, material):
    client.force_login(user)
    run = _start_run(client, machine)
    assert _record_state(client, run, material, '0.000', '0.000').status_code == 302
    snapshot = ProductionRunMaterialState.objects.get()
    assert snapshot.roll_quantity == Decimal('0.000')
    assert snapshot.spare_roll_quantity == Decimal('0.000')


@pytest.mark.django_db
def test_model_rejects_foreign_material_and_negative_quantity(
    user, factory, material, other_material
):
    run = ProductionRun.objects.create(
        factory=factory,
        reference='PR-STATE-MODEL',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=timezone.now(),
        created_by=user,
    )
    with pytest.raises(ValidationError):
        ProductionRunMaterialState.objects.create(
            production_run=run,
            material=other_material,
            roll_quantity=Decimal('1.000'),
            spare_roll_quantity=Decimal('0.000'),
        )
    with pytest.raises(ValidationError):
        ProductionRunMaterialState.objects.create(
            production_run=run,
            material=material,
            roll_quantity=Decimal('-1.000'),
            spare_roll_quantity=Decimal('0.000'),
        )


@pytest.mark.django_db
def test_multiple_materials_and_snapshots_preserved(
    client, user, machine, material, second_material
):
    client.force_login(user)
    run = _start_run(client, machine)
    _record_state(client, run, material, '8.000', '1.000')
    _record_state(client, run, second_material, '4.000', '3.000')
    _record_state(client, run, material, '6.500', '0.500')
    assert ProductionRunMaterialState.objects.filter(production_run=run).count() == 3
    page = client.get(reverse('dashboard:production_run', args=[run.pk]))
    assert page.status_code == 200
    assert b'6.500' in page.content
    assert b'0.500' in page.content
    assert b'TIS-STATE-001' in page.content
    assert b'SAP-001' in page.content
    current = page.context['current_material_states']
    by_code = {item.material.code: item for item in current}
    assert by_code['SAP-001'].roll_quantity == Decimal('6.500')
    assert by_code['TIS-STATE-001'].roll_quantity == Decimal('4.000')


@pytest.mark.django_db
def test_completed_run_cannot_receive_material_state(
    client, user, machine, material
):
    client.force_login(user)
    run = _start_run(client, machine)
    client.post(reverse('dashboard:production_complete', args=[run.pk]))
    assert client.get(
        reverse('dashboard:production_material_state', args=[run.pk])
    ).status_code == 404
    assert _record_state(client, run, material).status_code == 404
    assert ProductionRunMaterialState.objects.count() == 0


@pytest.mark.django_db
def test_empty_material_state_renders(client, user, machine):
    client.force_login(user)
    run = _start_run(client, machine)
    response = client.get(reverse('dashboard:production_run', args=[run.pk]))
    assert b'No machine roll or spare roll state recorded on this run yet.' in response.content
    assert b'Record material state' in response.content


@pytest.mark.django_db
def test_material_state_does_not_modify_inventory(
    client, user, factory, machine, material
):
    batch = MaterialBatch.objects.create(material=material, lot_number='STATE-LOT-1')
    stock = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=timezone.now().date(),
        opening_quantity=Decimal('100.000'),
        closing_quantity=Decimal('90.000'),
    )
    addition = MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=batch,
        quantity=Decimal('40.000'),
    )
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        consumed_at=timezone.now(),
    )
    client.force_login(user)
    run = _start_run(client, machine)
    _record_state(client, run, material, '12.000', '3.000')
    stock.refresh_from_db()
    addition.refresh_from_db()
    consumption.refresh_from_db()
    assert stock.opening_quantity == Decimal('100.000')
    assert stock.closing_quantity == Decimal('90.000')
    assert addition.quantity == Decimal('40.000')
    assert consumption.quantity == Decimal('5.000')
    assert MaterialConsumption.objects.filter(pk=consumption.pk).count() == 1
