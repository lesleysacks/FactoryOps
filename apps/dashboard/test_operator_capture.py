"""
Tests for M3.5 operator capture — FactoryOps UI, not Django Admin.
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
    StockRecord,
    UnitOfMeasure,
)


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='supervisor1',
        email='sup@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.fixture
def admin_user(db, factory):
    return User.objects.create_user(
        username='admin1',
        email='admin@factoryops.local',
        password='Password123!',
        role=User.Role.ADMIN,
        factory=factory,
        is_staff=True,
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
        code='RES-001',
        category=category,
        unit=unit,
    )


@pytest.fixture
def machine(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Press 1',
        code='MC-001',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def inactive_machine(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Retired Press',
        code='MC-OFF',
        status=MachineStatus.DECOMMISSIONED,
        is_active=False,
    )


@pytest.fixture
def other_machine(db, other_factory):
    line = ProductionLine.objects.create(factory=other_factory, name='South Line', code='S1')
    return Machine.objects.create(
        production_line=line,
        name='South Press',
        code='MC-SOUTH',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.mark.django_db
def test_operator_dashboard_requires_login(client):
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_anonymous_users_redirect_from_capture(client):
    for name in (
        'operator_production',
        'operator_inventory',
        'stock_count_create',
        'material_receipt_create',
    ):
        response = client.get(reverse(f'dashboard:{name}'))
        assert response.status_code == 302
        assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_operator_sees_operator_dashboard(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 200
    assert b'Operator dashboard' in response.content
    assert b'Record stock count' in response.content
    assert b'Record receipt' in response.content
    assert b'admin:materials' not in response.content
    assert b'>Admin<' not in response.content
    assert b'>Orders<' not in response.content
    assert b'>Reports<' not in response.content


@pytest.mark.django_db
def test_operator_navigation_includes_floor_sections(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator'))
    assert b'Operations' in response.content
    assert b'Production' in response.content
    assert b'Inventory' in response.content


@pytest.mark.django_db
def test_operator_cannot_open_supervisor_inventory_dashboard(client, user):
    client.force_login(user)
    assert client.get(reverse('dashboard:inventory')).status_code == 403
    assert client.get(reverse('dashboard:supervisor')).status_code == 403
    assert client.get(reverse('dashboard:manager')).status_code == 403
    assert client.get(reverse('dashboard:executive')).status_code == 403


@pytest.mark.django_db
def test_operator_cannot_access_another_factory_machine(
    client, user, other_machine
):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator_machine', args=[other_machine.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_operator_production_hides_other_factory_and_inactive_machines(
    client, user, machine, inactive_machine, other_machine
):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator_production'))
    assert response.status_code == 200
    assert b'MC-001' in response.content
    assert b'MC-OFF' not in response.content
    assert b'MC-SOUTH' not in response.content


@pytest.mark.django_db
def test_inactive_machine_cannot_be_opened(client, user, inactive_machine):
    client.force_login(user)
    response = client.get(
        reverse('dashboard:operator_machine', args=[inactive_machine.pk])
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_operator_can_open_own_factory_machine(client, user, machine):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator_machine', args=[machine.pk]))
    assert response.status_code == 200
    assert b'MC-001' in response.content


@pytest.mark.django_db
def test_operator_cannot_submit_another_factory_material(
    client, user, other_material
):
    client.force_login(user)
    response = client.post(reverse('dashboard:stock_count_create'), {
        'material': other_material.pk,
        'opening_quantity': '10.000',
    })
    assert response.status_code == 200
    assert StockRecord.objects.filter(material=other_material).count() == 0
    assert b'Select a valid choice' in response.content


@pytest.mark.django_db
def test_stock_count_form_validation(client, user):
    client.force_login(user)
    response = client.post(reverse('dashboard:stock_count_create'), {})
    assert response.status_code == 200
    assert StockRecord.objects.count() == 0
    assert b'This field is required' in response.content


@pytest.mark.django_db
def test_valid_stock_count_submission(client, user, material):
    client.force_login(user)
    response = client.post(reverse('dashboard:stock_count_create'), {
        'material': material.pk,
        'opening_quantity': '12.500',
    })
    assert response.status_code == 302
    assert response.url == reverse('dashboard:operator')
    record = StockRecord.objects.get(material=material)
    assert record.factory_id == user.factory_id
    assert record.opening_quantity == Decimal('12.500')
    assert record.closing_quantity is None
    assert record.recording_date == timezone.now().date()


@pytest.mark.django_db
def test_successful_submission_shows_factoryops_confirmation(client, user, material):
    client.force_login(user)
    response = client.post(
        reverse('dashboard:material_receipt_create'),
        {
            'material': material.pk,
            'lot_number': ' LOT-FLOOR-1 ',
            'quantity': '8.000',
        },
        follow=True,
    )
    assert response.status_code == 200
    assert b'Entry recorded successfully.' in response.content
    addition = MaterialAddition.objects.get(material=material)
    assert addition.factory_id == user.factory_id
    assert addition.quantity == Decimal('8.000')
    assert addition.batch.lot_number == 'LOT-FLOOR-1'


@pytest.mark.django_db
def test_csrf_protected_stock_count_post(user, material):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.post(reverse('dashboard:stock_count_create'), {
        'material': material.pk,
        'opening_quantity': '3.000',
    })
    assert response.status_code == 403
    assert StockRecord.objects.count() == 0


@pytest.mark.django_db
def test_stock_count_form_includes_csrf(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:stock_count_create'))
    assert response.status_code == 200
    assert b'csrfmiddlewaretoken' in response.content
    assert b'Record stock count' in response.content


@pytest.mark.django_db
def test_stock_count_dropdown_shows_active_factory_materials(client, user, material):
    client.force_login(user)
    response = client.get(reverse('dashboard:stock_count_create'))
    assert response.status_code == 200
    html = response.content.decode()
    assert f'<option value="{material.pk}">' in html
    assert 'SAP-001' in html
    assert 'Select a material' in html


@pytest.mark.django_db
def test_stock_count_dropdown_hides_foreign_factory_materials(
    client, user, material, other_material
):
    client.force_login(user)
    response = client.get(reverse('dashboard:stock_count_create'))
    html = response.content.decode()
    assert f'<option value="{material.pk}">' in html
    assert f'value="{other_material.pk}"' not in html
    assert 'RES-001' not in html


@pytest.mark.django_db
def test_stock_count_dropdown_hides_inactive_materials(client, user, material):
    material.is_active = False
    material.save()
    client.force_login(user)
    response = client.get(reverse('dashboard:stock_count_create'))
    html = response.content.decode()
    assert f'value="{material.pk}"' not in html
    assert 'SAP-001' not in html
    assert 'Select a material' in html


@pytest.mark.django_db
def test_stock_count_dropdown_empty_when_factory_has_no_materials(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:stock_count_create'))
    html = response.content.decode()
    assert 'Select a material' in html
    assert Material.objects.filter(factory=user.factory).count() == 0
    assert response.context['form'].fields['material'].queryset.count() == 0


@pytest.mark.django_db
def test_material_admin_defaults_factory_to_user_factory(supervisor):
    from django.contrib.admin.sites import AdminSite
    from django.test import RequestFactory

    from apps.materials.admin import MaterialAdmin

    request = RequestFactory().get('/admin/materials/material/add/')
    request.user = supervisor
    initial = MaterialAdmin(Material, AdminSite()).get_changeform_initial_data(request)
    assert initial['factory'] == supervisor.factory_id


@pytest.mark.django_db
def test_operator_cannot_close_another_factory_stock_record(
    client, user, other_factory, other_material
):
    record = StockRecord.objects.create(
        factory=other_factory,
        material=other_material,
        recording_date=timezone.now().date(),
        opening_quantity=Decimal('4.000'),
    )
    client.force_login(user)
    response = client.post(
        reverse('dashboard:stock_count_close', args=[record.pk]),
        {'closing_quantity': '3.000'},
    )
    assert response.status_code == 404
    record.refresh_from_db()
    assert record.closing_quantity is None


@pytest.mark.django_db
def test_supervisor_access_remains_functional(client, supervisor):
    client.force_login(supervisor)
    assert client.get(reverse('dashboard:supervisor')).status_code == 200
    assert client.get(reverse('dashboard:inventory')).status_code == 200
    assert client.get(reverse('dashboard:operator')).status_code == 200
    assert client.get(reverse('dashboard:executive')).status_code == 403


@pytest.mark.django_db
def test_manager_and_executive_access_remain_functional(client, admin_user):
    client.force_login(admin_user)
    assert client.get(reverse('dashboard:manager')).status_code == 200
    assert client.get(reverse('dashboard:executive')).status_code == 200
    assert client.get(reverse('dashboard:inventory')).status_code == 200
    response = client.get(reverse('dashboard:manager'))
    assert b'>Orders<' in response.content or b'Orders' in response.content
    assert b'Reports' in response.content
    assert b'Admin' in response.content


@pytest.mark.django_db
def test_receipt_reuses_existing_batch(client, user, material):
    batch = MaterialBatch.objects.create(material=material, lot_number='SAP-DASH-01')
    client.force_login(user)
    client.post(reverse('dashboard:material_receipt_create'), {
        'material': material.pk,
        'lot_number': batch.lot_number,
        'quantity': '2.000',
    })
    assert MaterialBatch.objects.filter(material=material).count() == 1
    assert MaterialAddition.objects.get(material=material).batch_id == batch.pk
