"""Report pages follow supervisor and admin access, scoped to the user's factory."""

from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.factories.models import Factory
from apps.production.models import ProductionOutput, ProductionRun
from apps.reports.services import daily_production_summary


DAY = date(2026, 10, 20)


def _output(factory, reference, quantity):
    started = datetime(2026, 10, 20, 8, 0, tzinfo=datetime_timezone.utc)
    run = ProductionRun.objects.create(
        factory=factory,
        reference=reference,
        started_at=started,
        ended_at=started,
    )
    return ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=quantity,
        recorded_at=started,
    )


def _user(username, role, factory):
    return User.objects.create_user(
        username=username,
        email=f'{username}@factoryops.local',
        password='Password123!',
        role=role,
        factory=factory,
    )


@pytest.mark.django_db
def test_anonymous_users_are_sent_to_login(client):
    for name in ('production_summary', 'qc_variance'):
        response = client.get(reverse(f'reports:{name}'))
        assert response.status_code == 302
        assert '/accounts/login/' in response.url


@pytest.mark.django_db
@pytest.mark.parametrize('role', [User.Role.OPERATOR, User.Role.QC])
def test_operator_and_qc_cannot_open_reports(client, factory, role):
    person = _user(f'report-{role.lower()}', role, factory)
    client.force_login(person)
    for name in ('production_summary', 'qc_variance'):
        assert client.get(reverse(f'reports:{name}')).status_code == 403


@pytest.mark.django_db
def test_supervisor_and_plant_admin_can_open_reports(client, factory):
    for role, username in (
        (User.Role.SUPERVISOR, 'report-open-supervisor'),
        (User.Role.ADMIN, 'report-open-admin'),
    ):
        person = _user(username, role, factory)
        client.force_login(person)
        for name in ('production_summary', 'qc_variance'):
            response = client.get(reverse(f'reports:{name}'))
            assert response.status_code == 200
            assert b'UTC' in response.content


@pytest.mark.django_db
def test_supervisor_page_hides_the_other_factory(client, factory):
    _output(factory, 'PR-VISIBLE', Decimal('8'))
    other = Factory.objects.create(name='South Plant')
    _output(other, 'PR-SECRET', Decimal('9'))
    supervisor = _user('report-scope-supervisor', User.Role.SUPERVISOR, factory)
    client.force_login(supervisor)

    response = client.get(reverse('reports:production_summary'), {
        'start': DAY.isoformat(),
        'end': DAY.isoformat(),
    })

    body = response.content.decode()
    assert response.status_code == 200
    assert '8.000' in body
    assert 'PR-SECRET' not in body
    assert 'South Plant' not in body
    assert '9.000' not in body


@pytest.mark.django_db
def test_unassigned_supervisor_page_is_empty(client, factory):
    _output(factory, 'PR-SECRET', Decimal('8'))
    supervisor = _user('report-blank-factory', User.Role.SUPERVISOR, None)
    client.force_login(supervisor)

    response = client.get(reverse('reports:qc_variance'), {'preset': 'day'})

    body = response.content.decode()
    assert response.status_code == 200
    assert 'not assigned to a factory' in body
    assert 'PR-SECRET' not in body


@pytest.mark.django_db
def test_admin_without_a_factory_sees_every_factory(factory):
    _output(factory, 'PR-EAST', Decimal('8'))
    other = Factory.objects.create(name='West Plant')
    _output(other, 'PR-WEST', Decimal('9'))
    platform = _user('report-platform-admin', User.Role.ADMIN, None)

    summary = daily_production_summary(platform, DAY)

    assert summary['output_quantity'] == Decimal('17.000')
    assert summary['run_count'] == 2


@pytest.mark.django_db
def test_plant_admin_stays_inside_one_factory(factory):
    _output(factory, 'PR-EAST', Decimal('8'))
    other = Factory.objects.create(name='West Plant')
    _output(other, 'PR-WEST', Decimal('9'))
    plant_admin = _user('report-plant-admin', User.Role.ADMIN, factory)

    summary = daily_production_summary(plant_admin, DAY)

    assert summary['output_quantity'] == Decimal('8.000')


@pytest.mark.django_db
def test_operator_navigation_has_no_output_reports_link(client, user):
    client.force_login(user)
    response = client.get(reverse('dashboard:operator'))
    assert b'Output reports' not in response.content
    assert b'>Reports<' not in response.content


@pytest.mark.django_db
def test_supervisor_navigation_links_to_output_reports(client, factory):
    supervisor = _user('report-nav-supervisor', User.Role.SUPERVISOR, factory)
    client.force_login(supervisor)
    response = client.get(reverse('dashboard:supervisor'))
    assert reverse('reports:production_summary') in response.content.decode()
    assert b'Output reports' in response.content
