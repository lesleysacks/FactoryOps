"""
Tests for M4A operator production workflow.

Extends ProductionRun / ProductionOutput. Does not cover consumption, QC,
or reconciliation.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.dashboard.services import operator_dashboard
from apps.factories.models import Factory, ProductionLine
from apps.machines.models import Machine, MachineStatus
from apps.production.models import (
    ProductionOutput,
    ProductionRun,
    ProductionRunStatus,
)


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='prod_supervisor',
        email='prod-sup@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.fixture
def admin_user(db, factory):
    return User.objects.create_user(
        username='prod_admin',
        email='prod-admin@factoryops.local',
        password='Password123!',
        role=User.Role.ADMIN,
        factory=factory,
        is_staff=True,
    )


@pytest.fixture
def qc_user(db, factory):
    return User.objects.create_user(
        username='prod_qc',
        email='prod-qc@factoryops.local',
        password='Password123!',
        role=User.Role.QC,
        factory=factory,
    )


@pytest.fixture
def other_factory(db):
    return Factory.objects.create(name='South Plant', location='Building 2')


@pytest.fixture
def other_line(db, other_factory):
    return ProductionLine.objects.create(
        factory=other_factory,
        name='South Line',
        code='S1',
    )


@pytest.fixture
def other_machine(db, other_line):
    return Machine.objects.create(
        production_line=other_line,
        name='South Press',
        code='MC-SOUTH-PROD',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def machine(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Press 1',
        code='MC-PROD-001',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def inactive_machine(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Retired Press',
        code='MC-PROD-OFF',
        status=MachineStatus.DECOMMISSIONED,
        is_active=False,
    )


@pytest.fixture
def second_line(db, factory):
    return ProductionLine.objects.create(
        factory=factory,
        name='Line 2',
        code='L2',
    )


@pytest.fixture
def second_machine(db, second_line):
    return Machine.objects.create(
        production_line=second_line,
        name='Press 2',
        code='MC-PROD-002',
        status=MachineStatus.OPERATIONAL,
    )


def _start(client, machine, extra=None):
    data = extra or {}
    return client.post(reverse('dashboard:machine_start', args=[machine.pk]), data)


@pytest.mark.django_db
def test_production_page_requires_authentication(client):
    response = client.get(reverse('dashboard:operator_production'))
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_operator_can_access_production(client, user, machine):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator_production'))
    assert response.status_code == 200
    assert b'Production lines' in response.content
    assert b'Line 1' in response.content
    assert b'MC-PROD-001' in response.content
    assert b'No active production runs.' in response.content
    assert b'No completed production runs today.' in response.content


@pytest.mark.django_db
def test_supervisor_can_access_production(client, supervisor, machine):
    client.force_login(supervisor)
    response = client.get(reverse('dashboard:operator_production'))
    assert response.status_code == 200
    assert b'MC-PROD-001' in response.content


@pytest.mark.django_db
def test_admin_can_access_production(client, admin_user, machine):
    client.force_login(admin_user)
    response = client.get(reverse('dashboard:operator_production'))
    assert response.status_code == 200
    assert b'Start run' in response.content or b'Production lines' in response.content


@pytest.mark.django_db
def test_operator_cannot_access_another_factory_production_data(
    client, user, machine, other_machine
):
    other_run = ProductionRun.objects.create(
        factory=other_machine.production_line.factory,
        production_line=other_machine.production_line,
        machine=other_machine,
        reference='PR-FOREIGN-001',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=timezone.now(),
    )
    client.force_login(user)
    response = client.get(reverse('dashboard:operator_production'))
    assert b'MC-SOUTH-PROD' not in response.content
    assert b'PR-FOREIGN-001' not in response.content
    assert client.get(
        reverse('dashboard:production_line', args=[other_machine.production_line_id])
    ).status_code == 404
    assert client.get(
        reverse('dashboard:production_run', args=[other_run.pk])
    ).status_code == 404


@pytest.mark.django_db
def test_foreign_production_line_rejected(client, user, other_line):
    client.force_login(user)
    response = client.post(
        reverse('dashboard:production_line', args=[other_line.pk]),
        {'machine': 1},
    )
    assert response.status_code == 404
    assert ProductionRun.objects.count() == 0


@pytest.mark.django_db
def test_foreign_machine_rejected(client, user, other_machine):
    client.force_login(user)
    response = _start(client, other_machine)
    assert response.status_code == 404
    assert ProductionRun.objects.count() == 0


@pytest.mark.django_db
def test_machine_from_another_line_rejected(
    client, user, production_line, second_machine
):
    client.force_login(user)
    response = client.post(
        reverse('dashboard:production_line', args=[production_line.pk]),
        {'machine': second_machine.pk},
    )
    assert response.status_code == 200
    assert ProductionRun.objects.count() == 0
    assert b'Select a valid choice' in response.content


@pytest.mark.django_db
def test_inactive_machine_rejected(client, user, inactive_machine, production_line):
    client.force_login(user)
    assert _start(client, inactive_machine).status_code == 404
    response = client.post(
        reverse('dashboard:production_line', args=[production_line.pk]),
        {'machine': inactive_machine.pk},
    )
    assert response.status_code == 200
    assert ProductionRun.objects.count() == 0


@pytest.mark.django_db
def test_valid_run_can_be_started(client, user, machine):
    client.force_login(user)
    before = timezone.now()
    response = _start(
        client,
        machine,
        {
            'started_at': '2019-01-01 00:00:00',
            'factory': 999,
            'created_by': 999,
        },
    )
    assert response.status_code == 302
    run = ProductionRun.objects.get()
    assert response.url == reverse('dashboard:production_run', args=[run.pk])
    assert run.status == ProductionRunStatus.IN_PROGRESS
    assert run.factory_id == user.factory_id
    assert run.production_line_id == machine.production_line_id
    assert run.machine_id == machine.pk
    assert run.created_by_id == user.pk
    assert run.started_at is not None
    assert run.started_at >= before
    assert run.started_at.year != 2019
    assert run.ended_at is None
    assert run.reference.startswith(f"PR-{timezone.now().date().strftime('%Y%m%d')}-")


@pytest.mark.django_db
def test_started_at_user_and_factory_are_server_side(client, user, machine):
    client.force_login(user)
    _start(client, machine)
    run = ProductionRun.objects.get()
    assert run.started_at is not None
    assert run.created_by == user
    assert run.factory == user.factory


@pytest.mark.django_db
def test_valid_output_can_be_recorded(client, user, machine):
    client.force_login(user)
    _start(client, machine)
    run = ProductionRun.objects.get()
    response = client.post(
        reverse('dashboard:production_run', args=[run.pk]),
        {'output_name': ' Crates ', 'quantity': '25.500'},
    )
    assert response.status_code == 302
    output = ProductionOutput.objects.get()
    assert output.production_run_id == run.pk
    assert output.output_name == 'Crates'
    assert output.quantity == Decimal('25.500')
    assert output.recorded_at is not None


@pytest.mark.django_db
def test_output_quantity_must_be_positive(client, user, machine):
    client.force_login(user)
    _start(client, machine)
    run = ProductionRun.objects.get()
    url = reverse('dashboard:production_run', args=[run.pk])
    for quantity in ('0', '-1', '0.000'):
        response = client.post(url, {'output_name': 'Crates', 'quantity': quantity})
        assert response.status_code == 200
        assert ProductionOutput.objects.count() == 0


@pytest.mark.django_db
def test_completed_run_cannot_receive_output(client, user, machine):
    client.force_login(user)
    _start(client, machine)
    run = ProductionRun.objects.get()
    client.post(reverse('dashboard:production_complete', args=[run.pk]))
    response = client.post(
        reverse('dashboard:production_run', args=[run.pk]),
        {'output_name': 'Crates', 'quantity': '1.000'},
    )
    assert response.status_code == 200
    assert ProductionOutput.objects.count() == 0


@pytest.mark.django_db
def test_run_can_be_completed(client, user, machine):
    client.force_login(user)
    _start(client, machine)
    run = ProductionRun.objects.get()
    before = timezone.now()
    response = client.post(reverse('dashboard:production_complete', args=[run.pk]))
    assert response.status_code == 302
    run.refresh_from_db()
    assert run.status == ProductionRunStatus.COMPLETED
    assert run.ended_at is not None
    assert run.ended_at >= before
    assert run.ended_at >= run.started_at


@pytest.mark.django_db
def test_run_cannot_be_completed_twice(client, user, machine):
    client.force_login(user)
    _start(client, machine)
    run = ProductionRun.objects.get()
    complete_url = reverse('dashboard:production_complete', args=[run.pk])
    client.post(complete_url)
    run.refresh_from_db()
    ended_at = run.ended_at
    response = client.post(complete_url, follow=True)
    assert response.status_code == 200
    assert b'already completed' in response.content
    run.refresh_from_db()
    assert run.status == ProductionRunStatus.COMPLETED
    assert run.ended_at == ended_at


@pytest.mark.django_db
def test_foreign_run_cannot_be_accessed(client, user, other_machine):
    run = ProductionRun.objects.create(
        factory=other_machine.production_line.factory,
        production_line=other_machine.production_line,
        machine=other_machine,
        reference='PR-FOREIGN-002',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=timezone.now(),
    )
    client.force_login(user)
    assert client.get(reverse('dashboard:production_run', args=[run.pk])).status_code == 404
    assert client.post(
        reverse('dashboard:production_run', args=[run.pk]),
        {'output_name': 'Crates', 'quantity': '1.000'},
    ).status_code == 404
    assert client.post(
        reverse('dashboard:production_complete', args=[run.pk])
    ).status_code == 404
    run.refresh_from_db()
    assert run.status == ProductionRunStatus.IN_PROGRESS
    assert ProductionOutput.objects.count() == 0


@pytest.mark.django_db
def test_dashboard_production_metrics_use_real_data(client, user, machine):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 200
    assert b'Active Runs' in response.content
    assert b"Today's Production" in response.content
    assert b'Completed Runs' in response.content
    assert b'No production activity recorded yet.' in response.content
    metrics = operator_dashboard(user)
    assert metrics['active_run_count'] == 0
    assert metrics['production_total'] == Decimal('0.000')
    assert metrics['completed_run_count_today'] == 0

    _start(client, machine)
    run = ProductionRun.objects.get()
    client.post(
        reverse('dashboard:production_run', args=[run.pk]),
        {'output_name': 'Crates', 'quantity': '10.000'},
    )
    client.post(reverse('dashboard:production_complete', args=[run.pk]))
    metrics = operator_dashboard(user)
    assert metrics['active_run_count'] == 0
    assert metrics['production_total'] == Decimal('10.000')
    assert metrics['completed_run_count_today'] == 1
    dash = client.get(reverse('dashboard:operator'))
    assert b'PR-' in dash.content
    assert b'No production activity recorded yet.' not in dash.content


@pytest.mark.django_db
def test_empty_production_state_renders(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator_production'))
    assert response.status_code == 200
    assert b'No production lines are set up for this factory.' in response.content
    assert b'No machines are available on your lines.' in response.content
    assert b'No active production runs.' in response.content


@pytest.mark.django_db
def test_qc_cannot_start_or_complete_production(client, qc_user, machine):
    client.force_login(qc_user)
    assert client.get(reverse('dashboard:operator_production')).status_code == 200
    assert _start(client, machine).status_code == 403
    assert ProductionRun.objects.count() == 0


@pytest.mark.django_db
def test_supervisor_and_admin_can_start_runs(
    client, supervisor, admin_user, machine, second_machine
):
    client.force_login(supervisor)
    assert _start(client, machine).status_code == 302
    client.force_login(admin_user)
    assert _start(client, second_machine).status_code == 302
    assert ProductionRun.objects.count() == 2


@pytest.mark.django_db
def test_inactive_machine_rejected_at_model_layer(user, factory, inactive_machine):
    with pytest.raises(ValidationError):
        ProductionRun.objects.create(
            factory=factory,
            production_line=inactive_machine.production_line,
            machine=inactive_machine,
            created_by=user,
            reference='PR-INACTIVE-001',
            status=ProductionRunStatus.IN_PROGRESS,
            started_at=timezone.now(),
        )


@pytest.mark.django_db
def test_machine_must_belong_to_selected_line(
    user, factory, production_line, second_machine
):
    with pytest.raises(ValidationError):
        ProductionRun.objects.create(
            factory=factory,
            production_line=production_line,
            machine=second_machine,
            created_by=user,
            reference='PR-LINE-MISMATCH-001',
            status=ProductionRunStatus.IN_PROGRESS,
            started_at=timezone.now(),
        )
