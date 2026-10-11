"""V1 pilot responsibilities for named staff. Accounts are fixtures, not live rows."""

from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.accounts.access import INVENTORY, PRINTING_STATION, ensure_responsibility_groups
from apps.accounts.management.commands.assign_pilot_staff import (
    apply_pilot_assignments,
    plan_pilot_assignments,
)
from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.catalog.services import seed_sanitary_catalog
from apps.factories.models import Factory, ProductionLine
from apps.machines.models import Machine, MachineStatus
from apps.materials.models import MaterialBatch, MaterialConsumption, StockRecord
from apps.production.models import (
    FinishedGood,
    ProductionOutput,
    ProductionRun,
    ProductionRunStatus,
    ProductionStage,
)
from apps.production.qc import add_qc_photo
from apps.production.state_machine import accept_variance, create_controlled_run, transition
from apps.production.workflow import start_production_run


PASSWORD = 'Password123!'


def _grant(user, *codes):
    groups = ensure_responsibility_groups()
    for code in codes:
        user.groups.add(groups[code])
    return user


def _user(username, factory, role, first_name=''):
    return User.objects.create_user(
        username=username,
        first_name=first_name,
        password=PASSWORD,
        role=role,
        factory=factory,
    )


@pytest.fixture
def press(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Printing press',
        code='MC-PRINT-1',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def spare_press(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Spare press',
        code='MC-PRINT-2',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def lesley(db, factory, press):
    user = _user('lsacks', factory, Role.OPERATOR, first_name='Lesley')
    _grant(user, PRINTING_STATION)
    user.assigned_machines.add(press)
    return user


@pytest.fixture
def neville(db, factory):
    user = _user('nsmith', factory, Role.OPERATOR, first_name='Neville')
    return _grant(user, INVENTORY)


@pytest.fixture
def yolandi(db, factory):
    return _user('yolandi', factory, Role.QC, first_name='Yolandi')


@pytest.fixture
def frankie(db, factory):
    return _user('frankie', factory, Role.SUPERVISOR, first_name='Frankie')


@pytest.fixture
def batch(db, material):
    return MaterialBatch.objects.create(material=material, lot_number='LOT-PILOT-1')


@pytest.fixture
def catalog(factory):
    seed_sanitary_catalog(factory)
    from apps.catalog.models import Packaging, Product

    product = Product.objects.get(factory=factory, code='SANITARY-PADS')
    return {
        'product': product,
        'variant': product.variants.get(code='MAXIS'),
        'packaging': Packaging.objects.get(factory=factory, code="15's"),
    }


def _configured(actor, catalog, machine):
    return create_controlled_run(
        actor,
        product=catalog['product'],
        variant=catalog['variant'],
        packaging=catalog['packaging'],
        line=machine.production_line,
        machine=machine,
        planned_pack_quantity=Decimal('20'),
    )


@pytest.mark.django_db
def test_permissions_follow_responsibility_not_the_persons_name(client, factory, press):
    named_without_duty = _user('lsacks', factory, Role.OPERATOR, first_name='Lesley')
    other_with_duty = _user('pat', factory, Role.OPERATOR, first_name='Pat')
    _grant(other_with_duty, PRINTING_STATION)
    other_with_duty.assigned_machines.add(press)

    client.force_login(named_without_duty)
    assert client.get(reverse('dashboard:operator_inventory')).status_code == 200
    client.force_login(other_with_duty)
    assert client.get(reverse('dashboard:operator_inventory')).status_code == 403
    assert client.get(reverse('dashboard:operator_production')).status_code == 200


@pytest.mark.django_db
def test_lesley_printing_station_is_limited_to_the_assigned_machine(
    client, lesley, press, spare_press, factory, catalog, material
):
    assert client.login(username='lsacks', password=PASSWORD)
    assert lesley.role == Role.OPERATOR
    assert lesley.is_superuser is False
    home = client.get(reverse('dashboard:operator'))
    html = home.content.decode()
    assert reverse('dashboard:operator_production') in html
    assert reverse('dashboard:operator_inventory') not in html
    assert b'Record stock count' not in home.content
    assert b'Start production' in home.content

    assert client.get(reverse('dashboard:operator_production')).status_code == 200
    assert client.get(reverse('dashboard:configure_run')).status_code == 200
    assert client.get(reverse('dashboard:operator_inventory')).status_code == 403
    assert client.get(reverse('dashboard:stock_count_create')).status_code == 403
    assert client.post(
        reverse('dashboard:stock_count_create'),
        {'material': material.pk, 'opening_quantity': '4.000'},
    ).status_code == 403
    assert StockRecord.objects.count() == 0
    assert client.get(reverse('dashboard:qc_queue')).status_code == 403
    assert client.get(reverse('dashboard:supervisor')).status_code == 403

    before = ProductionRun.objects.count()
    forged = client.post(reverse('dashboard:configure_run'), {
        'product': catalog['product'].pk,
        'variant': catalog['variant'].pk,
        'packaging': catalog['packaging'].pk,
        'production_line': spare_press.production_line_id,
        'machine': spare_press.pk,
        'planned_pack_quantity': '20',
        'factory': factory.pk,
        'created_by': lesley.pk,
        'status': ProductionRunStatus.COMPLETED,
    })
    assert forged.status_code == 200
    assert ProductionRun.objects.count() == before
    assert client.post(
        reverse('dashboard:machine_start', args=[spare_press.pk])
    ).status_code == 404

    other = Factory.objects.create(name='Other Plant')
    other_line = ProductionLine.objects.create(factory=other, name='Other', code='O1')
    foreign = Machine.objects.create(
        production_line=other_line,
        name='Foreign press',
        code='MC-FOREIGN',
        status=MachineStatus.OPERATIONAL,
    )
    assert client.post(
        reverse('dashboard:machine_start', args=[foreign.pk]),
        HTTP_ACCEPT='application/json',
    ).status_code == 404

    started = client.post(reverse('dashboard:machine_start', args=[press.pk]))
    assert started.status_code == 302
    run = ProductionRun.objects.get()
    assert run.machine_id == press.id
    assert run.factory_id == factory.id
    assert run.created_by_id == lesley.id
    assert client.get(
        reverse('dashboard:production_consumption', args=[run.pk])
    ).status_code == 403

    configured = client.post(reverse('dashboard:configure_run'), {
        'product': catalog['product'].pk,
        'variant': catalog['variant'].pk,
        'packaging': catalog['packaging'].pk,
        'production_line': press.production_line_id,
        'machine': press.pk,
        'planned_pack_quantity': '20',
        'factory': other.pk,
        'created_by': 99999,
        'status': ProductionRunStatus.COMPLETED,
    })
    assert configured.status_code == 302
    controlled = ProductionRun.objects.exclude(pk=run.pk).get()
    assert controlled.created_by_id == lesley.id
    assert controlled.factory_id == factory.id
    assert controlled.machine_id == press.id
    assert controlled.status != ProductionRunStatus.COMPLETED


@pytest.mark.django_db
def test_neville_inventory_cannot_manage_production(
    client, neville, lesley, press, material, batch, factory
):
    run = start_production_run(lesley, press)
    client.force_login(neville)
    page = client.get(reverse('dashboard:operator'))
    assert reverse('dashboard:operator_inventory') in page.content.decode()
    assert reverse('dashboard:operator_production') not in page.content.decode()
    assert b'Record stock count' in page.content
    assert b'Start production' not in page.content

    denied_gets = (
        'operator_production',
        'configure_run',
        'qc_queue',
        'supervisor',
        'inventory',
    )
    for name in denied_gets:
        response = client.get(
            reverse(f'dashboard:{name}'),
            HTTP_ACCEPT='application/json',
        )
        assert response.status_code == 403, name

    assert client.get(reverse('dashboard:production_run', args=[run.pk])).status_code == 403
    assert client.get(reverse('dashboard:production_line', args=[press.production_line_id])).status_code == 403
    assert client.get(reverse('dashboard:operator_machine', args=[press.pk])).status_code == 403
    assert client.get(reverse('dashboard:production_material_state', args=[run.pk])).status_code == 403
    for name in (
        'machine_start',
        'production_complete',
        'cancel_controlled_run',
        'start_controlled_run',
        'mark_output_recorded',
        'submit_for_qc',
    ):
        assert client.post(reverse(f'dashboard:{name}', args=[run.pk if name != 'machine_start' else press.pk])).status_code == 403

    assert client.get(reverse('dashboard:production_consumption', args=[run.pk])).status_code == 200
    recorded = client.post(reverse('dashboard:production_consumption', args=[run.pk]), {
        'material': material.pk,
        'batch': batch.pk,
        'quantity': '1.500',
    })
    assert recorded.status_code == 302
    assert MaterialConsumption.objects.filter(recorded_by=neville, batch=batch).count() == 1

    opened = client.post(reverse('dashboard:stock_count_create'), {
        'material': material.pk,
        'opening_quantity': '8.000',
    })
    assert opened.status_code == 302
    assert StockRecord.objects.filter(factory=factory, material=material).count() == 1

    other = Factory.objects.create(name='Neville Other')
    from apps.materials.models import Material, MaterialCategory, UnitOfMeasure
    category = MaterialCategory.objects.create(factory=other, name='Raw')
    unit = UnitOfMeasure.objects.create(name='Gram', symbol='g-pilot')
    foreign_material = Material.objects.create(
        factory=other,
        name='Foreign',
        code='FOR-1',
        category=category,
        unit=unit,
    )
    forged = client.post(reverse('dashboard:stock_count_create'), {
        'material': foreign_material.pk,
        'opening_quantity': '3.000',
        'factory': other.pk,
    })
    assert forged.status_code == 200
    assert not StockRecord.objects.filter(material=foreign_material).exists()
    run.refresh_from_db()
    assert run.status == ProductionRunStatus.IN_PROGRESS


@pytest.mark.django_db
def test_yolandi_cannot_open_production_run_management(
    client, yolandi, frankie, press, catalog
):
    run = _configured(frankie, catalog, press)
    client.force_login(yolandi)
    assert yolandi.role == Role.QC
    assert yolandi.role != Role.OPERATOR
    home = client.get('/dashboard/')
    assert home.status_code == 302
    assert home.url == reverse('dashboard:qc_queue')

    queue = client.get(reverse('dashboard:qc_queue'), HTTP_ACCEPT='application/json')
    assert queue.status_code == 200
    assert reverse('dashboard:operator_production') not in queue.content.decode()
    assert reverse('dashboard:configure_run') not in queue.content.decode()

    for name in (
        'operator',
        'operator_production',
        'operator_inventory',
        'configure_run',
        'stock_count_create',
        'material_receipt_create',
        'supervisor',
        'manager',
        'exception_queue',
    ):
        assert client.get(reverse(f'dashboard:{name}')).status_code == 403, name
    for name, pk in (
        ('production_run', run.pk),
        ('production_line', press.production_line_id),
        ('operator_machine', press.pk),
        ('production_consumption', run.pk),
        ('production_material_state', run.pk),
    ):
        assert client.get(reverse(f'dashboard:{name}', args=[pk])).status_code == 403
        assert client.post(
            reverse(f'dashboard:{name}', args=[pk]),
            {'quantity': '1', 'output_name': 'Tampered', 'form': 'details'},
        ).status_code == 403
    for name, pk in (
        ('machine_start', press.pk),
        ('production_complete', run.pk),
        ('cancel_controlled_run', run.pk),
        ('start_controlled_run', run.pk),
        ('mark_output_recorded', run.pk),
        ('submit_for_qc', run.pk),
    ):
        assert client.post(reverse(f'dashboard:{name}', args=[pk])).status_code == 403

    yolandi.is_staff = True
    yolandi.save(update_fields=['is_staff'])
    admin_page = client.get(reverse('admin:production_productionrun_changelist'))
    assert admin_page.status_code == 403
    exported = client.get('/admin/production/productionrun/export/')
    assert exported.status_code != 200
    api = client.get('/api/production/runs/', HTTP_ACCEPT='application/json')
    assert api.status_code != 200
    with pytest.raises(ValidationError):
        accept_variance(run, actor=yolandi, reason='Override the hold')


@pytest.mark.django_db
def test_yolandi_qc_screen_shows_context_without_changing_output(
    client, yolandi, frankie, press, catalog, material, batch, factory
):
    run = _configured(frankie, catalog, press)
    run = transition(run, ProductionStage.PRODUCTION_ACTIVE, actor=frankie)
    from apps.materials.workflow import record_material_consumption
    record_material_consumption(frankie, run.pk, material, batch, Decimal('2.000'))
    good = FinishedGood.objects.create(factory=factory, code='FG-PAD', name='Pad carton')
    output = ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=Decimal('9.000'),
        finished_good=good,
    )
    run = transition(run, ProductionStage.OUTPUT_RECORDED, actor=frankie)
    run = transition(run, ProductionStage.QC_REQUIRED, actor=frankie)
    add_qc_photo(
        yolandi,
        run,
        SimpleUploadedFile('mark.jpg', b'\xff\xd8\xff\xd9', content_type='image/jpeg'),
        caption='Expiry stamp',
    )
    client.force_login(yolandi)
    page = client.get(reverse('dashboard:qc_verification', args=[run.pk]))
    assert page.status_code == 200
    html = page.content.decode()
    assert catalog['product'].name in html
    assert press.code in html
    assert batch.lot_number in html
    assert 'FG-PAD' in html
    assert "15&#x27;s" in html or "15's" in html
    assert 'Expiry stamp' in html
    assert reverse('dashboard:production_run', args=[run.pk]) not in html
    assert 'name="expiry"' not in html

    client.post(reverse('dashboard:production_run', args=[run.pk]), {
        'output_name': 'Changed',
        'quantity': '1.000',
    })
    client.post(reverse('dashboard:qc_verification', args=[run.pk]), {
        'form': 'details',
        'variant': catalog['variant'].pk,
        'packaging': catalog['packaging'].pk,
        'qc_verified_quantity': '1.000',
    })
    output.refresh_from_db()
    assert output.quantity == Decimal('9.000')
    assert output.output_name == 'Pads'


@pytest.mark.django_db
def test_frankie_supervisor_can_start_a_run_and_is_not_a_superuser(
    client, frankie, press, catalog
):
    assert frankie.is_superuser is False
    assert frankie.is_staff is False
    assert client.login(username='frankie', password=PASSWORD)
    assert client.get(reverse('dashboard:supervisor')).status_code == 200
    assert client.get(reverse('dashboard:inventory')).status_code == 200
    assert client.get(reverse('dashboard:manager')).status_code == 403
    assert client.get(reverse('admin:index')).status_code == 302

    started = client.post(reverse('dashboard:machine_start', args=[press.pk]))
    assert started.status_code == 302
    assert ProductionRun.objects.filter(created_by=frankie).count() == 1

    controlled = _configured(frankie, catalog, press)
    with pytest.raises(ValidationError):
        accept_variance(controlled, actor=frankie, reason='Skip QC')
    event = AuditEvent.objects.filter(actor=frankie).first()
    assert event is not None
    with pytest.raises(ValidationError):
        event.delete()
    assert AuditEvent.objects.filter(pk=event.pk).exists()
    frankie.refresh_from_db()
    assert frankie.is_superuser is False


@pytest.mark.django_db
def test_pilot_assignment_dry_run_writes_nothing_and_apply_is_idempotent(factory, press):
    before_users = User.objects.count()
    before_groups = Group.objects.count()
    plan = plan_pilot_assignments()
    assert plan['can_apply'] is False
    assert plan['applied'] is False
    assert {person['status'] for person in plan['people']} == {'missing'}
    out = StringIO()
    call_command('assign_pilot_staff', stdout=out)
    assert 'dry-run' in out.getvalue()
    assert User.objects.count() == before_users
    assert Group.objects.count() == before_groups
    with pytest.raises(CommandError):
        call_command('assign_pilot_staff', '--apply', stdout=StringIO())
    assert User.objects.count() == before_users

    lesley = _user('lesley', factory, Role.OPERATOR, first_name='Someone')
    neville = _user('stores', factory, Role.QC, first_name='Neville')
    yolandi = _user('inspector', factory, Role.OPERATOR, first_name='Yolandi')
    frankie = _user('lead', factory, Role.OPERATOR, first_name='Frankie')
    lesley_hash = lesley.password
    frankie_staff = frankie.is_staff
    plan = plan_pilot_assignments()
    assert plan['can_apply'] is True
    text = StringIO()
    call_command('assign_pilot_staff', stdout=text)
    report = text.getvalue()
    assert 'Lesley: resolved' in report
    assert 'Assigned printing machines' in report
    assert lesley.password not in report

    applied = apply_pilot_assignments()
    assert applied['applied'] is True
    lesley.refresh_from_db()
    neville.refresh_from_db()
    yolandi.refresh_from_db()
    frankie.refresh_from_db()
    assert lesley.role == Role.OPERATOR
    assert set(lesley.groups.values_list('name', flat=True)) == {PRINTING_STATION}
    assert lesley.assigned_machines.count() == 0
    assert lesley.password == lesley_hash
    assert neville.role == Role.OPERATOR
    assert set(neville.groups.values_list('name', flat=True)) == {INVENTORY}
    assert yolandi.role == Role.QC
    assert yolandi.groups.filter(name__in=[PRINTING_STATION, INVENTORY]).count() == 0
    assert frankie.role == Role.SUPERVISOR
    assert frankie.is_superuser is False
    assert frankie.is_staff is frankie_staff
    apply_pilot_assignments()
    lesley.refresh_from_db()
    assert lesley.password == lesley_hash
    assert set(lesley.groups.values_list('name', flat=True)) == {PRINTING_STATION}

    _user('lesley-2', factory, Role.OPERATOR, first_name='Lesley')
    blocked = plan_pilot_assignments()
    assert blocked['can_apply'] is False
    assert any(person['status'] == 'ambiguous' for person in blocked['people'])
    yolandi_role = yolandi.role
    refused = apply_pilot_assignments()
    assert refused['applied'] is False
    yolandi.refresh_from_db()
    assert yolandi.role == yolandi_role

    superuser = User.objects.create_superuser(
        username='root-frankie',
        email='root@factoryops.local',
        password=PASSWORD,
        first_name='Frankie',
    )
    super_plan = plan_pilot_assignments()
    frankie_row = next(person for person in super_plan['people'] if person['label'] == 'Frankie')
    assert frankie_row['status'] == 'ambiguous'
    assert superuser.is_superuser is True
