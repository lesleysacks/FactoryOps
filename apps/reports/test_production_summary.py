"""Production summaries read ProductionOutput and leave those rows unchanged."""

from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.factories.models import Factory
from apps.production.models import ProductionOutput, ProductionRun, QCVerification
from apps.reports.services import (
    daily_production_summary,
    production_summary,
    weekly_production_summary,
)
from apps.reports.windows import resolve_window


DAY = date(2026, 10, 20)


def _utc(year, month, day, hour, minute, second=0):
    return datetime(
        year, month, day, hour, minute, second, tzinfo=datetime_timezone.utc,
    )


def _run(factory, reference):
    started = _utc(2026, 10, 1, 8, 0)
    return ProductionRun.objects.create(
        factory=factory,
        reference=reference,
        started_at=started,
        ended_at=started,
    )


def _output(run, quantity, recorded_at):
    return ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=quantity,
        recorded_at=recorded_at,
    )


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='report-supervisor',
        email='reports-sup@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.mark.django_db
def test_utc_midnight_is_the_day_boundary(supervisor, factory):
    run = _run(factory, 'PR-BOUNDARY')
    _output(run, Decimal('5'), _utc(2026, 10, 20, 0, 0, 0))
    _output(run, Decimal('7'), _utc(2026, 10, 19, 23, 59, 59))
    _output(run, Decimal('9'), _utc(2026, 10, 21, 0, 0, 0))

    summary = daily_production_summary(supervisor, DAY)

    assert summary['timezone_label'] == 'UTC'
    assert summary['output_quantity'] == Decimal('5.000')
    assert summary['output_count'] == 1
    assert summary['run_count'] == 1
    assert summary['days'][0]['date'] == DAY
    assert summary['days'][0]['output_quantity'] == Decimal('5.000')


@pytest.mark.django_db
def test_same_day_outputs_sum_and_count_the_run_once(supervisor, factory):
    run = _run(factory, 'PR-SAME-DAY')
    _output(run, Decimal('1.500'), _utc(2026, 10, 20, 1, 0))
    _output(run, Decimal('2.500'), _utc(2026, 10, 20, 18, 0))

    summary = daily_production_summary(supervisor, DAY)

    assert summary['output_quantity'] == Decimal('4.000')
    assert summary['output_count'] == 2
    assert summary['run_count'] == 1


@pytest.mark.django_db
def test_weekly_total_equals_the_seven_daily_rows(supervisor, factory):
    run = _run(factory, 'PR-WEEK')
    _output(run, Decimal('1'), _utc(2026, 10, 14, 12, 0))
    _output(run, Decimal('2'), _utc(2026, 10, 20, 12, 0))
    _output(run, Decimal('100'), _utc(2026, 10, 21, 0, 0))

    summary = weekly_production_summary(supervisor, DAY)

    assert summary['day_count'] == 7
    assert summary['start'] == date(2026, 10, 14)
    assert summary['end'] == DAY
    assert summary['output_quantity'] == Decimal('3.000')
    assert sum(day['output_quantity'] for day in summary['days']) == Decimal('3.000')
    assert [day['output_quantity'] for day in summary['days']].count(Decimal('0.000')) == 5


@pytest.mark.django_db
def test_summary_uses_operator_output_not_qc_quantity(supervisor, factory):
    run = _run(factory, 'PR-QC-IGNORED')
    _output(run, Decimal('50'), _utc(2026, 10, 20, 9, 0))
    QCVerification.objects.create(
        production_run=run,
        expected_quantity=Decimal('40'),
        recorded_quantity=Decimal('50'),
        qc_verified_quantity=Decimal('1'),
    )

    summary = daily_production_summary(supervisor, DAY)

    assert summary['output_quantity'] == Decimal('50.000')


@pytest.mark.django_db
def test_other_factory_output_is_excluded(supervisor, factory):
    own = _run(factory, 'PR-OWN')
    _output(own, Decimal('8'), _utc(2026, 10, 20, 9, 0))
    other_factory = Factory.objects.create(name='West Plant')
    other = _run(other_factory, 'PR-OTHER')
    _output(other, Decimal('9'), _utc(2026, 10, 20, 9, 0))

    summary = daily_production_summary(supervisor, DAY)

    assert summary['output_quantity'] == Decimal('8.000')


@pytest.mark.django_db
def test_user_without_a_factory_sees_no_output(db, factory):
    unassigned = User.objects.create_user(
        username='report-unassigned',
        email='unassigned@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=None,
    )
    _output(_run(factory, 'PR-HIDDEN'), Decimal('8'), _utc(2026, 10, 20, 9, 0))

    summary = daily_production_summary(unassigned, DAY)

    assert summary['output_quantity'] == Decimal('0.000')
    assert summary['output_count'] == 0


@pytest.mark.django_db
def test_reading_the_summary_does_not_change_output(supervisor, factory):
    output = _output(
        _run(factory, 'PR-UNCHANGED'),
        Decimal('12'),
        _utc(2026, 10, 20, 9, 0),
    )
    updated_at = output.updated_at

    daily_production_summary(supervisor, DAY)

    output.refresh_from_db()
    assert output.quantity == Decimal('12.000')
    assert output.updated_at == updated_at


@pytest.mark.django_db
def test_custom_range_rejects_more_than_ninety_three_days_on_the_page(client, supervisor, factory):
    _output(_run(factory, 'PR-LONG'), Decimal('15'), _utc(2026, 10, 20, 9, 0))
    client.force_login(supervisor)
    start = DAY - timedelta(days=93)
    response = client.get(reverse('reports:production_summary'), {
        'start': start.isoformat(),
        'end': DAY.isoformat(),
    })

    assert response.status_code == 200
    body = response.content.decode()
    assert 'at most 93 calendar days' in body
    assert 'PR-LONG' not in body
    assert '15.000' not in body


@pytest.mark.django_db
def test_week_page_labels_the_utc_window(client, supervisor):
    client.force_login(supervisor)
    response = client.get(reverse('reports:production_summary'), {'preset': 'week'})
    body = response.content.decode()
    assert response.status_code == 200
    assert 'Weekly production summary' in body
    assert 'UTC' in body


@pytest.mark.django_db
def test_service_window_can_be_any_inclusive_span(supervisor, factory):
    run = _run(factory, 'PR-SPAN')
    _output(run, Decimal('4'), _utc(2026, 2, 1, 0, 0))
    _output(run, Decimal('6'), _utc(2026, 2, 3, 23, 59, 59))
    window = resolve_window('2026-02-01', '2026-02-03', today=DAY)

    summary = production_summary(supervisor, window)

    assert summary['day_count'] == 3
    assert summary['output_quantity'] == Decimal('10.000')
    assert summary['days'][1]['output_quantity'] == Decimal('0.000')
