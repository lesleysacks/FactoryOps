"""Django admin must not bypass pilot role and factory limits.

These accounts are test fixtures. They are not the factory PC users.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.access import INVENTORY, PRINTING_STATION, ensure_responsibility_groups
from apps.accounts.admin import UserAdmin
from apps.accounts.models import Role, User
from apps.factories.models import Factory
from apps.machines.models import Machine, MachineStatus
from apps.materials.admin import StockRecordAdmin
from apps.materials.models import Material, MaterialCategory, StockRecord, UnitOfMeasure
from apps.production.admin import ProductionOutputAdmin, ProductionRunAdmin
from apps.production.models import (
    ProductionOutput,
    ProductionRun,
    QCVerification,
)
from apps.production.workflow import start_production_run


def _grant_group(user, code):
    groups = ensure_responsibility_groups()
    user.groups.add(groups[code])
    return user


def _grant_model_perms(user, model):
    content_type = ContentType.objects.get_for_model(model)
    user.user_permissions.add(*Permission.objects.filter(content_type=content_type))
    return User.objects.get(pk=user.pk)


def _person(username, factory, role, *, staff=False, first_name=''):
    return User.objects.create_user(
        username=username,
        first_name=first_name,
        password='Password123!',
        role=role,
        factory=factory,
        is_staff=staff,
    )


@pytest.fixture
def press(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Printing press',
        code='MC-ADMIN-1',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def spare_press(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Spare press',
        code='MC-ADMIN-2',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def lesley(factory, press):
    user = _person('lsacks-admin', factory, Role.OPERATOR, staff=True, first_name='Lesley')
    _grant_group(user, PRINTING_STATION)
    user.assigned_machines.add(press)
    return user


@pytest.fixture
def neville(factory):
    user = _person('nsmith-admin', factory, Role.OPERATOR, staff=True, first_name='Neville')
    return _grant_group(user, INVENTORY)


@pytest.fixture
def yolandi(factory):
    return _person('yolandi-admin', factory, Role.QC, staff=True, first_name='Yolandi')


@pytest.fixture
def frankie(factory):
    return _person('frankie-admin', factory, Role.SUPERVISOR, staff=True, first_name='Frankie')


@pytest.fixture
def plant_admin(factory):
    return _person('plant-admin', factory, Role.ADMIN, staff=True, first_name='Plant')


def _stock(factory, material, opening='4.000'):
    return StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date.today(),
        opening_quantity=Decimal(opening),
    )


def _foreign_material(name='Other Plant'):
    other = Factory.objects.create(name=name)
    category = MaterialCategory.objects.create(factory=other, name='Raw')
    unit = UnitOfMeasure.objects.create(name=f'Gram {other.pk}', symbol=f'g{other.pk}')
    material = Material.objects.create(
        factory=other,
        name='Foreign pulp',
        code=f'FOR-{other.pk}',
        category=category,
        unit=unit,
    )
    return other, material


@pytest.mark.django_db
def test_staff_printing_operator_cannot_open_stock_users_or_qc_in_admin(
    client, lesley, factory, material, press
):
    lesley = _grant_model_perms(lesley, StockRecord)
    lesley = _grant_model_perms(lesley, User)
    lesley = _grant_model_perms(lesley, QCVerification)
    lesley = _grant_model_perms(lesley, ProductionRun)
    client.force_login(lesley)

    denied = (
        'admin:materials_stockrecord_changelist',
        'admin:materials_stockrecord_add',
        'admin:accounts_user_changelist',
        'admin:auth_group_changelist',
        'admin:production_qcverification_changelist',
        'admin:factories_factory_changelist',
        'admin:audit_auditevent_changelist',
    )
    for name in denied:
        response = client.get(reverse(name))
        assert response.status_code == 403, name

    assert client.get(reverse('admin:production_productionrun_changelist')).status_code == 200
    assert client.post(
        reverse('dashboard:exception_detail', args=[1]),
        {'form': 'accept', 'reason': 'skip'},
    ).status_code == 403
    assert client.post(
        reverse('dashboard:qc_verification', args=[1]),
        {'form': 'complete'},
    ).status_code == 403
    assert StockRecord.objects.count() == 0

    home = client.get(reverse('dashboard:operator'))
    assert reverse('admin:index') not in home.content.decode()


@pytest.mark.django_db
def test_staff_inventory_operator_cannot_open_production_admin(
    client, neville, lesley, press, factory, material
):
    neville = _grant_model_perms(neville, ProductionRun)
    neville = _grant_model_perms(neville, ProductionOutput)
    neville = _grant_model_perms(neville, StockRecord)
    run = start_production_run(lesley, press)
    output = ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=Decimal('9.000'),
    )
    client.force_login(neville)
    assert client.get(reverse('admin:production_productionrun_changelist')).status_code == 403
    assert client.get(reverse('admin:production_productionoutput_changelist')).status_code == 403
    posted = client.post(
        reverse('admin:production_productionoutput_change', args=[output.pk]),
        {'quantity': '1.000', 'output_name': 'Tampered'},
    )
    assert posted.status_code == 403
    output.refresh_from_db()
    assert output.quantity == Decimal('9.000')
    assert output.output_name == 'Pads'

    assert client.get(reverse('admin:materials_stockrecord_changelist')).status_code == 200
    other, foreign = _foreign_material()
    foreign_stock = _stock(other, foreign, '3.000')
    hidden = client.get(reverse('admin:materials_stockrecord_change', args=[foreign_stock.pk]))
    assert hidden.status_code == 302
    assert reverse('admin:materials_stockrecord_change', args=[foreign_stock.pk]) not in hidden.url
    foreign_stock.refresh_from_db()
    assert foreign_stock.opening_quantity == Decimal('3.000')
    assert foreign_stock.factory_id == other.id
    listing = client.get(reverse('admin:materials_stockrecord_changelist'))
    change_url = reverse('admin:materials_stockrecord_change', args=[foreign_stock.pk])
    assert change_url.encode() not in listing.content
    assert foreign.code.encode() not in listing.content

    request = RequestFactory().post('/admin/materials/stockrecord/add/')
    request.user = neville
    forged = StockRecord(
        factory=other,
        material=foreign,
        recording_date=date.today(),
        opening_quantity=Decimal('1.000'),
    )
    with pytest.raises(PermissionDenied):
        StockRecordAdmin(StockRecord, AdminSite()).save_model(request, forged, None, False)
    assert StockRecord.objects.filter(factory=other).count() == 1

    kept = StockRecord(
        factory=other,
        material=material,
        recording_date=date.today(),
        opening_quantity=Decimal('2.000'),
    )
    StockRecordAdmin(StockRecord, AdminSite()).save_model(request, kept, None, False)
    kept.refresh_from_db()
    assert kept.factory_id == factory.id
    assert kept.material_id == material.id


@pytest.mark.django_db
def test_printing_admin_save_rejects_an_unassigned_machine(
    lesley, press, spare_press, factory
):
    request = RequestFactory().post('/admin/production/productionrun/add/')
    request.user = lesley
    admin = ProductionRunAdmin(ProductionRun, AdminSite())
    forged = ProductionRun(
        factory=factory,
        production_line=spare_press.production_line,
        machine=spare_press,
        reference='FORGED-SPARE',
        created_by=lesley,
    )
    with pytest.raises(PermissionDenied):
        admin.save_model(request, forged, None, False)
    assert not ProductionRun.objects.filter(reference='FORGED-SPARE').exists()

    allowed = ProductionRun(
        factory=factory,
        production_line=press.production_line,
        machine=press,
        reference='ASSIGNED-PRESS',
        created_by=lesley,
    )
    admin.save_model(request, allowed, None, False)
    saved = ProductionRun.objects.get(reference='ASSIGNED-PRESS')
    assert saved.machine_id == press.id
    assert saved.factory_id == factory.id

    output = ProductionOutput(
        production_run=saved,
        output_name='Pads',
        quantity=Decimal('9.000'),
    )
    ProductionOutputAdmin(ProductionOutput, AdminSite()).save_model(request, output, None, False)
    assert ProductionOutput.objects.get(production_run=saved).quantity == Decimal('9.000')


@pytest.mark.django_db
def test_qc_admin_is_readable_and_cannot_rewrite_recorded_quantity(
    client, yolandi, frankie, press, factory
):
    frankie.is_staff = False
    frankie.save(update_fields=['is_staff'])
    run = start_production_run(frankie, press)
    output = ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=Decimal('9.000'),
    )
    verification = QCVerification.objects.create(
        production_run=run,
        recorded_quantity=Decimal('9.000'),
        qc_verified_quantity=Decimal('8.000'),
    )
    yolandi = _grant_model_perms(yolandi, ProductionOutput)
    yolandi = _grant_model_perms(yolandi, QCVerification)
    client.force_login(yolandi)

    assert client.get(reverse('admin:production_productionoutput_change', args=[output.pk])).status_code == 403
    assert client.get(reverse('admin:production_qcverification_change', args=[verification.pk])).status_code == 200
    posted = client.post(
        reverse('admin:production_qcverification_change', args=[verification.pk]),
        {
            'recorded_quantity': '1.000',
            'qc_verified_quantity': '1.000',
            'status': 'VERIFIED',
        },
    )
    assert posted.status_code == 403
    verification.refresh_from_db()
    output.refresh_from_db()
    assert verification.recorded_quantity == Decimal('9.000')
    assert verification.qc_verified_quantity == Decimal('8.000')
    assert output.quantity == Decimal('9.000')

    queue = client.get(reverse('dashboard:qc_queue'))
    assert reverse('dashboard:operator') not in queue.content.decode()


@pytest.mark.django_db
def test_supervisor_staff_is_not_a_superuser_and_cannot_manage_users(
    client, frankie, plant_admin, factory, press
):
    frankie = _grant_model_perms(frankie, User)
    client.force_login(frankie)
    assert frankie.is_superuser is False
    assert client.get(reverse('admin:accounts_user_changelist')).status_code == 403
    assert client.get(reverse('admin:factories_factory_changelist')).status_code == 403
    assert client.get(reverse('admin:production_productionrun_changelist')).status_code == 200
    assert client.get(reverse('admin:materials_stockrecord_changelist')).status_code == 200
    assert client.get(reverse('admin:production_qcverification_changelist')).status_code == 200
    assert client.get(reverse('admin:audit_auditevent_changelist')).status_code == 200
    assert client.post(reverse('admin:audit_auditevent_add'), {}).status_code == 403

    target = _person('floor-operator', factory, Role.OPERATOR)
    request = RequestFactory().post('/admin/accounts/user/')
    request.user = plant_admin
    target.is_superuser = True
    UserAdmin(User, AdminSite()).save_model(request, target, None, True)
    target.refresh_from_db()
    assert target.is_superuser is False
    assert target.factory_id == factory.id

    root = User.objects.create_superuser(
        username='root-demo',
        email='root@factoryops.local',
        password='Password123!',
    )
    root.role = Role.OPERATOR
    with pytest.raises(PermissionDenied):
        UserAdmin(User, AdminSite()).save_model(request, root, None, True)
    root.refresh_from_db()
    assert root.is_superuser is True
    assert root.role == Role.ADMIN


@pytest.mark.django_db
def test_platform_admin_sees_every_factory_and_a_plant_admin_does_not(
    factory, material, plant_admin
):
    local = _stock(factory, material, '5.000')
    other, foreign = _foreign_material('Second Plant')
    remote = _stock(other, foreign, '6.000')
    platform = _person('platform-admin', None, Role.ADMIN, staff=True)
    request = RequestFactory().get('/admin/materials/stockrecord/')
    request.user = plant_admin
    plant_ids = set(
        StockRecordAdmin(StockRecord, AdminSite()).get_queryset(request).values_list('pk', flat=True)
    )
    assert plant_ids == {local.pk}
    request.user = platform
    platform_ids = set(
        StockRecordAdmin(StockRecord, AdminSite()).get_queryset(request).values_list('pk', flat=True)
    )
    assert platform_ids == {local.pk, remote.pk}


@pytest.mark.django_db
def test_model_permissions_do_not_open_admin_without_the_staff_flag(
    client, factory, material
):
    user = _person('lesley-floor', factory, Role.OPERATOR, staff=False, first_name='Lesley')
    _grant_group(user, PRINTING_STATION)
    user = _grant_model_perms(user, StockRecord)
    client.force_login(user)
    response = client.get(reverse('admin:materials_stockrecord_add'))
    assert response.status_code == 302
    assert '/admin/login/' in response.url
