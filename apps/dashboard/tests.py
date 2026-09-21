"""
Tests for Dashboard App — role views, permissions, and aggregations.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.dashboard.services import (
    executive_dashboard,
    inventory_dashboard,
    operator_dashboard,
    supervisor_dashboard,
)
from apps.factories.models import Factory
from apps.materials.models import (
    Material,
    MaterialAddition,
    MaterialBatch,
    MaterialCategory,
    MaterialConsumption,
    MaterialWaste,
    StockReconciliation,
    StockRecord,
)
from apps.production.models import (
    ProductionOutput,
    ProductionReject,
    ProductionRun,
    ProductionRunStatus,
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
def material_batch(db, material):
    return MaterialBatch.objects.create(
        material=material,
        lot_number='SAP-DASH-01',
    )


def _now():
    return timezone.now()


@pytest.mark.django_db
def test_unauthenticated_dashboard_redirects(client):
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_home_redirects_operator(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:home'))
    assert response.status_code == 302
    assert response.url == reverse('dashboard:operator')


@pytest.mark.django_db
def test_home_alias_matches_login_redirect(client, user):
    client.force_login(user)
    response = client.get('/dashboard/')
    assert response.status_code == 302
    assert response.url == reverse('dashboard:operator')


@pytest.mark.django_db
def test_operator_can_open_operator_dashboard(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 200
    assert b'Operator dashboard' in response.content


@pytest.mark.django_db
def test_operator_cannot_open_supervisor_dashboard(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:supervisor'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_operator_cannot_open_manager_or_executive(client, user):
    client.force_login(user)
    assert client.get(reverse('dashboard:manager')).status_code == 403
    assert client.get(reverse('dashboard:executive')).status_code == 403
    assert client.get(reverse('dashboard:inventory')).status_code == 403


@pytest.mark.django_db
def test_supervisor_can_open_supervisor_and_inventory(client, supervisor):
    client.force_login(supervisor)
    assert client.get(reverse('dashboard:supervisor')).status_code == 200
    assert client.get(reverse('dashboard:inventory')).status_code == 200
    assert client.get(reverse('dashboard:operator')).status_code == 200
    assert client.get(reverse('dashboard:executive')).status_code == 403


@pytest.mark.django_db
def test_admin_can_open_all_dashboards(client, admin_user):
    client.force_login(admin_user)
    for name in ('operator', 'supervisor', 'manager', 'executive', 'inventory'):
        response = client.get(reverse(f'dashboard:{name}'))
        assert response.status_code == 200


@pytest.mark.django_db
def test_operator_metrics_use_today_only(user, factory, material, material_batch):
    now = _now()
    yesterday = now - timedelta(days=1)
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('12.000'),
        consumed_at=now,
        production_reference='LINE-1',
    )
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('99.000'),
        consumed_at=yesterday,
    )
    MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('3.000'),
        occurred_at=now,
        reason='Trim',
    )
    MaterialAddition.objects.create(
        factory=factory,
        material=material,
        batch=material_batch,
        quantity=Decimal('40.000'),
        added_at=now,
    )
    ProductionRun.objects.create(
        factory=factory,
        reference='PR-TODAY-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=now,
    )
    metrics = operator_dashboard(user)
    assert metrics['consumption_total'] == Decimal('12.000')
    assert metrics['waste_total'] == Decimal('3.000')
    assert metrics['open_run_count'] == 1
    assert any(item.quantity == Decimal('40.000') for item in metrics['recent_additions'])
    assert metrics['consumption_today'][0].production_reference == 'LINE-1'


@pytest.mark.django_db
def test_dashboard_metrics_are_factory_scoped(user, factory, material, material_batch):
    other = Factory.objects.create(name='South Plant', location='Building 2')
    other_category = MaterialCategory.objects.create(factory=other, name='Raw Materials')
    unit = material.unit
    other_material = Material.objects.create(
        factory=other,
        name='SAP',
        code='SAP-001',
        category=other_category,
        unit=unit,
    )
    other_batch = MaterialBatch.objects.create(material=other_material, lot_number='SOUTH-01')
    now = _now()
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('5.000'),
        consumed_at=now,
    )
    MaterialConsumption.objects.create(
        factory=other,
        material=other_material,
        quantity=Decimal('80.000'),
        consumed_at=now,
    )
    MaterialAddition.objects.create(
        factory=other,
        material=other_material,
        batch=other_batch,
        quantity=Decimal('500.000'),
        added_at=now,
    )
    metrics = operator_dashboard(user)
    assert metrics['consumption_total'] == Decimal('5.000')
    assert all(item.factory_id == factory.id for item in metrics['recent_additions'])


@pytest.mark.django_db
def test_supervisor_aggregates_output_waste_and_rejects(
    supervisor, factory, material
):
    now = _now()
    run = ProductionRun.objects.create(
        factory=factory,
        reference='PR-SUP-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=now,
    )
    ProductionOutput.objects.create(
        production_run=run,
        output_name='Crates',
        quantity=Decimal('200.000'),
        recorded_at=now,
    )
    MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('7.000'),
        occurred_at=now,
        reason='Trim',
    )
    ProductionReject.objects.create(
        production_run=run,
        quantity=Decimal('4.000'),
        occurred_at=now,
        reason='Flash',
    )
    StockReconciliation.objects.create(
        factory=factory,
        material=material,
        reconciliation_date=now.date(),
    )
    metrics = supervisor_dashboard(supervisor)
    assert metrics['active_run_count'] == 1
    assert metrics['output_today'] == Decimal('200.000')
    assert metrics['waste_today'] == Decimal('7.000')
    assert metrics['rejects_today'] == Decimal('4.000')
    assert len(metrics['outstanding_material']) == 1
    assert len(metrics['output_trend']) == 7


@pytest.mark.django_db
def test_executive_totals_and_variance(admin_user, factory, material):
    now = _now()
    run = ProductionRun.objects.create(
        factory=factory,
        reference='PR-EX-001',
        status=ProductionRunStatus.COMPLETED,
        started_at=now - timedelta(hours=2),
        ended_at=now,
    )
    ProductionOutput.objects.create(
        production_run=run,
        output_name='Crates',
        quantity=Decimal('50.000'),
        recorded_at=now,
    )
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('15.000'),
        consumed_at=now,
    )
    MaterialWaste.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('2.000'),
        occurred_at=now,
        reason='Trim',
    )
    StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=now.date(),
        opening_quantity=Decimal('100.000'),
        closing_quantity=Decimal('80.000'),
    )
    reconciliation = StockReconciliation.objects.create(
        factory=factory,
        material=material,
        reconciliation_date=now.date(),
    )
    reconciliation.calculate()
    metrics = executive_dashboard(admin_user)
    assert metrics['output_total'] == Decimal('50.000')
    assert metrics['consumption_total'] == Decimal('15.000')
    assert metrics['waste_total'] == Decimal('2.000')
    assert metrics['unfulfilled_orders'] == 0
    assert any(
        rec.variance_quantity is not None for rec in metrics['significant_variances']
    )


@pytest.mark.django_db
def test_inventory_snapshot_uses_latest_stock_record(supervisor, factory, material):
    StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('10.000'),
        closing_quantity=Decimal('8.000'),
    )
    latest = StockRecord.objects.create(
        factory=factory,
        material=material,
        recording_date=date(2026, 10, 2),
        opening_quantity=Decimal('8.000'),
        closing_quantity=Decimal('6.500'),
    )
    metrics = inventory_dashboard(supervisor)
    assert len(metrics['material_snapshots']) == 1
    assert metrics['material_snapshots'][0].pk == latest.pk
    assert metrics['material_snapshots'][0].closing_quantity == Decimal('6.500')


@pytest.mark.django_db
def test_dashboard_does_not_alter_source_records(user, factory, material):
    now = _now()
    consumption = MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('9.000'),
        consumed_at=now,
    )
    operator_dashboard(user)
    consumption.refresh_from_db()
    assert consumption.quantity == Decimal('9.000')
    assert MaterialConsumption.objects.filter(pk=consumption.pk).count() == 1


@pytest.mark.django_db
def test_operator_dashboard_renders_aggregated_quantity(
    client, user, factory, material
):
    client.force_login(user)
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        quantity=Decimal('12.000'),
        consumed_at=_now(),
    )
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 200
    assert b'12.000' in response.content
    assert b"Today's Tasks" in response.content
    assert b"Today's Production" in response.content
    assert b'Operations' in response.content
    assert b'FactoryOps' in response.content
    assert b'Log out' in response.content


@pytest.mark.django_db
def test_login_page_uses_factoryops_branding(client):
    response = client.get(reverse('accounts:login'))
    assert response.status_code == 200
    assert b'FactoryOps' in response.content
    assert b'Production &amp; Inventory Intelligence' in response.content
    assert b'Username' in response.content
    assert b'Password' in response.content
    assert b'Enter your username' in response.content
    assert b'Enter your password' in response.content
    assert b'Welcome Back' not in response.content


@pytest.mark.django_db
def test_logout_returns_to_login(client, user):
    client.force_login(user)
    response = client.post(reverse('accounts:logout'))
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


def test_favicon_ico_returns_icon(client):
    response = client.get('/favicon.ico')
    assert response.status_code == 200
    assert response['Content-Type'] == 'image/x-icon'
    body = b''.join(response.streaming_content)
    assert body[:4] == b'\x00\x00\x01\x00'


def test_login_page_includes_favicon_assets(client):
    response = client.get(reverse('accounts:login'))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'img/favicon/favicon.ico' in content
    assert 'img/favicon/favicon.svg' in content
    assert 'img/favicon/apple-touch-icon.png' in content


@pytest.mark.django_db
def test_dashboard_includes_favicon_assets(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'img/favicon/favicon.ico' in content
    assert 'img/favicon/favicon.svg' in content
    assert 'img/favicon/apple-touch-icon.png' in content


@pytest.mark.django_db
def test_role_navigation_hides_manager_screens_from_operator(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator'))
    assert b'Operations' in response.content
    assert b'>Orders<' not in response.content
    assert b'>Reports<' not in response.content


@pytest.mark.django_db
def test_supervisor_dashboard_shows_traffic_light_metrics(client, supervisor):
    client.force_login(supervisor)
    response = client.get(reverse('dashboard:supervisor'))
    assert response.status_code == 200
    assert b'Active Runs' in response.content
    assert b'Waste Today' in response.content
    assert b'Rejects Today' in response.content
    assert b'Stock Variances' in response.content
    assert b'Production' in response.content
    assert b'Supervisor' in response.content
