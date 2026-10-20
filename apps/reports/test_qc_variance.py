"""QC variance report reads the production variance service and does not save."""

from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.factories.models import Factory
from apps.production.models import ProductionOutput, ProductionRun, QCVerification
from apps.production.variance import VARIANCE_EXCEPTION, VARIANCE_INSUFFICIENT, VARIANCE_OK
from apps.reports.services import qc_variance_report
from apps.reports.windows import window_for_day


DAY = date(2026, 10, 20)


def _utc(hour, minute=0, second=0, day=20):
    return datetime(2026, 10, day, hour, minute, second, tzinfo=datetime_timezone.utc)


def _run(factory, reference):
    started = _utc(8)
    return ProductionRun.objects.create(
        factory=factory,
        reference=reference,
        started_at=started,
        ended_at=started,
    )


def _output(run, quantity, recorded_at=None):
    return ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=quantity,
        recorded_at=recorded_at or _utc(9),
    )


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='qc-report-supervisor',
        email='qc-reports@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.mark.django_db
def test_variance_matches_the_stored_expected_recorded_and_qc_quantities(supervisor, factory):
    run = _run(factory, 'PR-VARIANCE')
    _output(run, Decimal('3400'))
    QCVerification.objects.create(
        production_run=run,
        expected_quantity=Decimal('3000'),
        recorded_quantity=Decimal('3400'),
        qc_verified_quantity=Decimal('3000'),
    )

    report = qc_variance_report(supervisor, window_for_day(DAY))

    assert len(report['rows']) == 1
    row = report['rows'][0]
    assert row['variance_status'] == VARIANCE_EXCEPTION
    assert row['expected_quantity'] == Decimal('3000.000')
    assert row['recorded_quantity'] == Decimal('3400.000')
    assert row['qc_verified_quantity'] == Decimal('3000.000')
    assert row['recorded_vs_expected'] == Decimal('400.000')
    assert row['qc_vs_recorded'] == Decimal('-400.000')
    assert row['operator_output_quantity'] == Decimal('3400.000')


@pytest.mark.django_db
def test_matching_quantities_are_ok(supervisor, factory):
    run = _run(factory, 'PR-OK')
    _output(run, Decimal('3000'))
    QCVerification.objects.create(
        production_run=run,
        expected_quantity=Decimal('3000'),
        recorded_quantity=Decimal('3000'),
        qc_verified_quantity=Decimal('3000'),
    )

    row = qc_variance_report(supervisor, window_for_day(DAY))['rows'][0]

    assert row['variance_status'] == VARIANCE_OK
    assert row['qc_vs_recorded'] == Decimal('0.000')


@pytest.mark.django_db
def test_missing_qc_is_insufficient_data_and_creates_nothing(supervisor, factory):
    run = _run(factory, 'PR-NO-QC')
    _output(run, Decimal('10'))
    before = QCVerification.objects.count()

    row = qc_variance_report(supervisor, window_for_day(DAY))['rows'][0]

    assert row['variance_status'] == VARIANCE_INSUFFICIENT
    assert row['qc_verified_quantity'] is None
    assert row['qc_record_status'] is None
    assert row['recorded_quantity'] == Decimal('10.000')
    assert row['expected_quantity'] is None
    assert QCVerification.objects.count() == before
    assert not QCVerification.objects.filter(production_run=run).exists()


@pytest.mark.django_db
def test_report_preserves_output_and_frozen_recorded_quantity(supervisor, factory):
    run = _run(factory, 'PR-FROZEN')
    output = _output(run, Decimal('15'))
    verification = QCVerification.objects.create(
        production_run=run,
        expected_quantity=Decimal('10'),
        recorded_quantity=Decimal('10'),
        qc_verified_quantity=Decimal('12'),
    )
    output_updated = output.updated_at
    verification_updated = verification.updated_at

    row = qc_variance_report(supervisor, window_for_day(DAY))['rows'][0]

    output.refresh_from_db()
    verification.refresh_from_db()
    assert output.quantity == Decimal('15.000')
    assert output.updated_at == output_updated
    assert verification.recorded_quantity == Decimal('10.000')
    assert verification.qc_verified_quantity == Decimal('12.000')
    assert verification.updated_at == verification_updated
    assert row['operator_output_quantity'] == Decimal('15.000')
    assert row['recorded_quantity'] == Decimal('10.000')
    assert row['qc_verified_quantity'] == Decimal('12.000')
    assert row['recorded_quantity'] != row['qc_verified_quantity']


@pytest.mark.django_db
def test_date_filter_selects_the_run_and_variance_uses_the_whole_run(supervisor, factory):
    run = _run(factory, 'PR-SPLIT')
    _output(run, Decimal('10'), _utc(9, day=19))
    _output(run, Decimal('5'), _utc(9, day=20))

    earlier = qc_variance_report(supervisor, window_for_day(date(2026, 10, 19)))
    later = qc_variance_report(supervisor, window_for_day(DAY))

    assert earlier['rows'][0]['operator_output_quantity'] == Decimal('15.000')
    assert later['rows'][0]['operator_output_quantity'] == Decimal('15.000')
    assert later['rows'][0]['run_id'] == run.pk


@pytest.mark.django_db
def test_other_factory_runs_are_omitted(supervisor, factory):
    _output(_run(factory, 'PR-HOME'), Decimal('4'))
    other = Factory.objects.create(name='North Plant')
    _output(_run(other, 'PR-AWAY'), Decimal('6'))

    references = [
        row['reference']
        for row in qc_variance_report(supervisor, window_for_day(DAY))['rows']
    ]

    assert references == ['PR-HOME']


@pytest.mark.django_db
def test_variance_page_does_not_rewrite_recorded_quantity(client, supervisor, factory):
    run = _run(factory, 'PR-PAGE')
    output = _output(run, Decimal('3400'))
    verification = QCVerification.objects.create(
        production_run=run,
        expected_quantity=Decimal('3000'),
        recorded_quantity=Decimal('3400'),
        qc_verified_quantity=Decimal('3000'),
    )
    client.force_login(supervisor)

    response = client.get(reverse('reports:qc_variance'), {
        'start': DAY.isoformat(),
        'end': DAY.isoformat(),
    })

    output.refresh_from_db()
    verification.refresh_from_db()
    assert response.status_code == 200
    body = response.content.decode()
    assert 'PR-PAGE' in body
    assert 'EXCEPTION' in body
    assert '-400.000' in body
    assert output.quantity == Decimal('3400.000')
    assert verification.recorded_quantity == Decimal('3400.000')
    assert verification.qc_verified_quantity == Decimal('3000.000')
