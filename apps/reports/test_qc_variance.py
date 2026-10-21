"""QC variance report reads the production variance service and does not save."""

from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.factories.models import Factory
from apps.production.models import ProductionOutput, ProductionRun, QCVerification
from apps.production.variance import VARIANCE_EXCEPTION, VARIANCE_INSUFFICIENT, VARIANCE_OK
from apps.reports.services import daily_production_summary, qc_variance_report
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
    summary = daily_production_summary(supervisor, DAY)

    assert earlier['rows'][0]['operator_output_quantity'] == Decimal('15.000')
    assert later['rows'][0]['operator_output_quantity'] == Decimal('15.000')
    assert later['rows'][0]['run_id'] == run.pk
    assert summary['output_quantity'] == Decimal('5.000')


@pytest.mark.django_db
def test_split_output_keeps_frozen_recorded_quantity_and_omits_missing_qc_outside_window(
    supervisor, factory,
):
    frozen_run = _run(factory, 'PR-FROZEN-SPLIT')
    inside = _output(frozen_run, Decimal('10'), _utc(9, day=20))
    outside = _output(frozen_run, Decimal('5'), _utc(9, day=19))
    verification = QCVerification.objects.create(
        production_run=frozen_run,
        expected_quantity=Decimal('8'),
        recorded_quantity=Decimal('8'),
        qc_verified_quantity=Decimal('8'),
    )
    missing_inside = _run(factory, 'PR-NO-QC-INSIDE')
    missing_output = _output(missing_inside, Decimal('3'), _utc(11, day=20))
    outside_only = _run(factory, 'PR-OUTSIDE-ONLY')
    outside_only_output = _output(outside_only, Decimal('7'), _utc(11, day=19))
    inside_updated = inside.updated_at
    outside_updated = outside.updated_at
    verification_updated = verification.updated_at
    missing_updated = missing_output.updated_at
    outside_only_updated = outside_only_output.updated_at
    qc_count = QCVerification.objects.count()

    summary = daily_production_summary(supervisor, DAY)
    rows = {
        row['reference']: row
        for row in qc_variance_report(supervisor, window_for_day(DAY))['rows']
    }

    assert summary['output_quantity'] == Decimal('13.000')
    assert rows['PR-FROZEN-SPLIT']['operator_output_quantity'] == Decimal('15.000')
    assert rows['PR-FROZEN-SPLIT']['recorded_quantity'] == Decimal('8.000')
    assert rows['PR-FROZEN-SPLIT']['qc_verified_quantity'] == Decimal('8.000')
    assert rows['PR-FROZEN-SPLIT']['variance_status'] == VARIANCE_OK
    assert rows['PR-NO-QC-INSIDE']['variance_status'] == VARIANCE_INSUFFICIENT
    assert rows['PR-NO-QC-INSIDE']['recorded_quantity'] == Decimal('3.000')
    assert rows['PR-NO-QC-INSIDE']['qc_verified_quantity'] is None
    assert 'PR-OUTSIDE-ONLY' not in rows
    inside.refresh_from_db()
    outside.refresh_from_db()
    verification.refresh_from_db()
    missing_output.refresh_from_db()
    outside_only_output.refresh_from_db()
    assert inside.quantity == Decimal('10.000')
    assert inside.updated_at == inside_updated
    assert outside.quantity == Decimal('5.000')
    assert outside.updated_at == outside_updated
    assert verification.recorded_quantity == Decimal('8.000')
    assert verification.qc_verified_quantity == Decimal('8.000')
    assert verification.updated_at == verification_updated
    assert missing_output.quantity == Decimal('3.000')
    assert missing_output.updated_at == missing_updated
    assert outside_only_output.quantity == Decimal('7.000')
    assert outside_only_output.updated_at == outside_only_updated
    assert QCVerification.objects.count() == qc_count
    assert not QCVerification.objects.filter(production_run=missing_inside).exists()


@pytest.mark.django_db
def test_qc_page_explains_selection_and_frozen_recorded_quantity(client, supervisor):
    client.force_login(supervisor)
    response = client.get(reverse('reports:qc_variance'), {'preset': 'week'})
    body = response.content.decode()
    assert response.status_code == 200
    assert 'production output was recorded on a UTC date in this range' in body
    assert 'Variance figures are for the whole run' in body
    assert 'frozen recorded quantity' in body
    assert 'does not save changes' in body
    assert 'rolling window, not a calendar week' in body


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
