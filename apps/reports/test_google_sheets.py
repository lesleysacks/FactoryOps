"""Google Sheets reporting. The Google API is mocked. No live credentials."""

import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.factories.models import Factory
from apps.machines.models import Machine
from apps.materials.models import MaterialAddition, MaterialBatch, MaterialConsumption, MaterialScrap, MaterialWaste
from apps.production.models import (
    FinishedGood,
    FinishedGoodAddition,
    FinishedGoodAdjustment,
    FinishedGoodAdjustmentType,
    FinishedGoodDispatch,
    ProductionOutput,
    ProductionRun,
    ProductionRunStatus,
    QCVerification,
    Warehouse,
)
from apps.reports.datasets import DATASETS, PRODUCTION_OUTPUT_COLUMNS, QC_RESULT_COLUMNS, STOCK_MOVEMENT_COLUMNS
from apps.reports.errors import SheetsCallError
from apps.reports.formatting import format_requests
from apps.reports.google_client import GoogleSheetsGateway, classify_transport_failure, load_service_account
from apps.reports.models import SheetSyncRecord, SheetSyncRun, SheetSyncStatus
from apps.reports.sync import run_sync
from config.settings.base import _flag

ROOT = Path(__file__).resolve().parents[2]
PERSONAL_EMAIL = 'personal.secret@example.com'
PERSONAL_NAME = 'PersonalOperator'
PERSONAL_EMPLOYEE = 'EMP-SECRET-99'
PERSONAL_NOTE = 'PERSONAL-RUN-NOTE'
PERSONAL_MATERIAL = 'PERSONAL-MATERIAL-NOTE'
PERSONAL_DISPATCH = 'PERSONAL-DISPATCH-NOTE'
KEY_MATERIAL = 'SUPERSECRETKEY'


class BoomGateway:
    def prepare(self, *args, **kwargs):
        raise AssertionError('Google was called')

    def source_key_rows(self, *args, **kwargs):
        raise AssertionError('Google was called')

    def write_rows(self, *args, **kwargs):
        raise AssertionError('Google was called')

    def append_rows(self, *args, **kwargs):
        raise AssertionError('Google was called')


class RecordingGateway:
    def __init__(self):
        self.sheets = {}
        self.calls = []
        self.fail_next_append = False
        self.append_error = None
        self.store_before_append_error = False

    def prepare(self, title, columns):
        self.calls.append(('prepare', title, columns))
        self.sheets.setdefault(title, {'columns': columns, 'rows': {}})

    def source_key_rows(self, title):
        self.calls.append(('read', title))
        rows = self.sheets[title]['rows']
        return {cells[0]: number for number, cells in rows.items() if cells}

    def write_rows(self, title, updates):
        self.calls.append(('write', title))
        for number, cells in updates:
            self.sheets[title]['rows'][number] = list(cells)

    def append_rows(self, title, rows):
        self.calls.append(('append', title))
        if self.fail_next_append and not self.store_before_append_error:
            self.fail_next_append = False
            raise self.append_error
        existing = self.sheets[title]['rows']
        number = max(existing) + 1 if existing else 2
        for cells in rows:
            existing[number] = list(cells)
            number += 1
        if self.fail_next_append:
            self.fail_next_append = False
            raise self.append_error
        return []

    def rows(self, title):
        return list(self.sheets.get(title, {}).get('rows', {}).values())


def _personal_user(factory):
    return User.objects.create_user(
        username=PERSONAL_NAME,
        email=PERSONAL_EMAIL,
        password='Password123!',
        first_name='SecretFirst',
        last_name='SecretLast',
        role=Role.OPERATOR,
        employee_id=PERSONAL_EMPLOYEE,
        factory=factory,
    )


def _output(factory, production_line, user):
    machine = Machine.objects.create(
        production_line=production_line,
        name='Press',
        code='MC-012',
    )
    run = ProductionRun.objects.create(
        factory=factory,
        production_line=production_line,
        machine=machine,
        created_by=user,
        reference='PR-100',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
        notes=PERSONAL_NOTE,
    )
    return ProductionOutput.objects.create(
        production_run=run,
        output_name='=SUM(A1)',
        quantity=Decimal('12.5'),
        recorded_at=datetime(2026, 10, 1, 16, 0, tzinfo=dt_timezone.utc),
    )


def _assert_personal_data_absent(cells):
    blob = '\n'.join(cells)
    for secret in (
        PERSONAL_EMAIL,
        PERSONAL_NAME,
        PERSONAL_EMPLOYEE,
        PERSONAL_NOTE,
        PERSONAL_MATERIAL,
        PERSONAL_DISPATCH,
        'SecretFirst',
        'SecretLast',
        KEY_MATERIAL,
    ):
        assert secret not in blob


@pytest.mark.django_db
def test_integration_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv('GOOGLE_SHEETS_ENABLED', raising=False)
    assert _flag('GOOGLE_SHEETS_ENABLED') is False
    source = (ROOT / 'config' / 'settings' / 'base.py').read_text(encoding='utf-8')
    assert "_flag('GOOGLE_SHEETS_ENABLED')" in source
    assert settings.GOOGLE_SHEETS_ENABLED is False
    result = run_sync(gateway=BoomGateway())
    assert result.outcome == 'disabled'
    assert SheetSyncRecord.objects.count() == 0
    assert SheetSyncRun.objects.count() == 0


@pytest.mark.django_db
def test_saving_a_source_row_does_not_enqueue_or_call_google(factory, production_line):
    user = _personal_user(factory)
    before_audit = AuditEvent.objects.count()
    output = _output(factory, production_line, user)
    assert SheetSyncRecord.objects.count() == 0
    result = run_sync(gateway=BoomGateway())
    assert result.outcome == 'disabled'
    output.refresh_from_db()
    assert output.quantity == Decimal('12.500')
    assert AuditEvent.objects.count() == before_audit


@pytest.mark.django_db
def test_production_output_mapping_and_sheet_format(factory, production_line):
    user = _personal_user(factory)
    output = _output(factory, production_line, user)
    gateway = RecordingGateway()
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('production_output',)):
        result = run_sync(gateway=gateway)
    assert result.outcome == 'ok'
    assert result.synced == 1
    prepared = gateway.calls[0]
    assert prepared[0] == 'prepare'
    assert prepared[1] == 'Production output'
    assert prepared[2] == PRODUCTION_OUTPUT_COLUMNS
    rows = gateway.rows('Production output')
    assert len(rows) == 1
    cells = rows[0]
    output.refresh_from_db()
    assert cells[0] == f'production_output:production.ProductionOutput:{output.pk}'
    assert cells[1] == str(output.pk)
    assert cells[2] == 'Main Factory'
    assert cells[3] == 'PR-100'
    assert cells[4] == 'In progress'
    assert cells[5] == ''
    assert cells[6] == 'Line 1 (L1)'
    assert cells[7] == 'MC-012'
    assert cells[11] == "'=SUM(A1)"
    assert cells[12] == ''
    assert cells[13] == '12.500'
    assert cells[14] == '2026-10-01 16:00:00'
    _assert_personal_data_absent(cells)
    record = SheetSyncRecord.objects.get()
    assert record.status == SheetSyncStatus.SYNCED
    assert record.payload == cells
    _assert_personal_data_absent(record.payload)
    requests = format_requests(11, PRODUCTION_OUTPUT_COLUMNS)
    assert requests[0]['updateSheetProperties']['properties']['gridProperties']['frozenRowCount'] == 1
    header_format = requests[1]['repeatCell']['cell']['userEnteredFormat']
    assert header_format['textFormat']['bold'] is True
    patterns = [
        item['repeatCell']['cell']['userEnteredFormat']['numberFormat']
        for item in requests
        if 'numberFormat' in item.get('repeatCell', {}).get('cell', {}).get('userEnteredFormat', {})
    ]
    assert {'type': 'NUMBER', 'pattern': '0.000'} in patterns
    assert {'type': 'DATE_TIME', 'pattern': 'yyyy-mm-dd hh:mm:ss'} in patterns
    assert any('setBasicFilter' in item for item in requests)


@pytest.mark.django_db
def test_qc_mapping_excludes_people_and_photo_files(factory, production_line):
    user = _personal_user(factory)
    output = _output(factory, production_line, user)
    verification = QCVerification.objects.create(
        production_run=output.production_run,
        expected_quantity=Decimal('10'),
        recorded_quantity=Decimal('12.5'),
        qc_verified_quantity=Decimal('12'),
        verified_by=user,
        verified_at=datetime(2026, 10, 1, 18, 30, tzinfo=dt_timezone.utc),
    )
    gateway = RecordingGateway()
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('qc_results',)):
        result = run_sync(gateway=gateway)
    assert result.outcome == 'ok'
    assert gateway.calls[0][2] == QC_RESULT_COLUMNS
    cells = gateway.rows('QC results')[0]
    assert cells[0] == f'qc_results:production.QCVerification:{verification.pk}'
    assert cells[3] == 'PR-100'
    assert cells[4] == 'Pending'
    assert cells[7] == '10.000'
    assert cells[8] == '12.500'
    assert cells[9] == '12.000'
    assert cells[10] == '2026-10-01 18:30:00'
    assert cells[11] == '0'
    headers = [column.header for column in QC_RESULT_COLUMNS]
    assert 'Photo count' in headers
    assert all('photo' not in header.lower() or header == 'Photo count' for header in headers)
    assert 'Verified by' not in headers
    _assert_personal_data_absent(cells)


@pytest.mark.django_db
def test_stock_movement_mapping_uses_existing_fields(factory, material):
    user = _personal_user(factory)
    material.notes = PERSONAL_MATERIAL
    material.save()
    batch = MaterialBatch.objects.create(material=material, lot_number='LOT-1')
    run = ProductionRun.objects.create(
        factory=factory,
        reference='PR-STOCK',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 2, 8, 0, tzinfo=dt_timezone.utc),
        notes=PERSONAL_NOTE,
    )
    when = datetime(2026, 10, 2, 9, 0, tzinfo=dt_timezone.utc)
    MaterialAddition.objects.create(
        factory=factory, material=material, batch=batch, quantity=Decimal('5'), added_at=when,
    )
    MaterialConsumption.objects.create(
        factory=factory,
        material=material,
        batch=batch,
        quantity=Decimal('1.25'),
        consumed_at=when,
        production_run=run,
        recorded_by=user,
    )
    MaterialWaste.objects.create(
        factory=factory, material=material, quantity=Decimal('0.5'), occurred_at=when, reason='Torn bag',
    )
    MaterialScrap.objects.create(
        factory=factory, material=material, quantity=Decimal('0.25'), occurred_at=when, reason='Edge trim',
    )
    finished = FinishedGood.objects.create(factory=factory, code='FG-1', name='Crate')
    warehouse = Warehouse.objects.create(factory=factory, code='WH-1', name='Main')
    FinishedGoodAddition.objects.create(
        warehouse=warehouse, finished_good=finished, quantity=Decimal('3'), added_at=when,
    )
    FinishedGoodAdjustment.objects.create(
        warehouse=warehouse,
        finished_good=finished,
        quantity=Decimal('1'),
        adjustment_type=FinishedGoodAdjustmentType.INCREASE,
        occurred_at=when,
        reason='Count correction',
    )
    FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished,
        quantity=Decimal('2'),
        dispatched_at=when,
        reference='DISP-100',
        notes=PERSONAL_DISPATCH,
    )
    gateway = RecordingGateway()
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('stock_movements',)):
        result = run_sync(gateway=gateway)
    assert result.outcome == 'ok'
    assert result.synced == 7
    assert gateway.calls[0][2] == STOCK_MOVEMENT_COLUMNS
    rows = gateway.rows('Stock movements')
    assert len(rows) == 7
    kinds = {row[2] for row in rows}
    assert kinds == {
        'material_addition',
        'material_consumption',
        'material_waste',
        'material_scrap',
        'finished_good_addition',
        'finished_good_adjustment',
        'finished_good_dispatch',
    }
    keys = [row[0] for row in rows]
    assert len(keys) == len(set(keys))
    addition = next(row for row in rows if row[2] == 'material_addition')
    assert addition[5] == 'SAP-001'
    assert addition[7] == '5.000'
    assert addition[8] == 'kg'
    assert addition[9] == 'LOT-1'
    consumption = next(row for row in rows if row[2] == 'material_consumption')
    assert consumption[11] == 'PR-STOCK'
    waste = next(row for row in rows if row[2] == 'material_waste')
    assert waste[13] == 'Torn bag'
    dispatch = next(row for row in rows if row[2] == 'finished_good_dispatch')
    assert dispatch[10] == 'WH-1'
    assert dispatch[13] == 'DISP-100'
    for row in rows:
        _assert_personal_data_absent(row)
    assert not list(__import__('django.apps', fromlist=['apps']).apps.get_app_config('downtime').get_models())
    assert not list(__import__('django.apps', fromlist=['apps']).apps.get_app_config('handovers').get_models())


@pytest.mark.django_db
def test_missing_datasets_are_reported_and_not_invented():
    gateway = BoomGateway()
    with override_settings(
        GOOGLE_SHEETS_ENABLED=True,
        GOOGLE_SHEETS_DATASETS=('downtime', 'shift_handovers', 'payroll'),
    ):
        result = run_sync(gateway=gateway)
    assert result.outcome == 'ok'
    assert 'Downtime' in result.message
    assert 'Shift handovers' in result.message
    assert 'payroll' in result.message
    assert {dataset.key for dataset in DATASETS if not dataset.available} == {'downtime', 'shift_handovers'}


@pytest.mark.django_db
def test_retries_update_the_same_row_and_a_lost_response_does_not_duplicate(factory, production_line):
    user = _personal_user(factory)
    output = _output(factory, production_line, user)
    gateway = RecordingGateway()
    gateway.fail_next_append = True
    gateway.store_before_append_error = True
    gateway.append_error = SheetsCallError(
        'timeout',
        f'timed out -----BEGIN PRIVATE KEY-----\n{KEY_MATERIAL}\n-----END PRIVATE KEY----- ya29.{KEY_MATERIAL}',
    )
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('production_output',)):
        first = run_sync(gateway=gateway)
        assert first.failed == 1
        assert len(gateway.rows('Production output')) == 1
        record = SheetSyncRecord.objects.get()
        assert record.status == SheetSyncStatus.PENDING
        assert KEY_MATERIAL not in record.last_error
        assert 'ya29' not in record.last_error
        output.refresh_from_db()
        original_pk = output.pk
        second = run_sync(gateway=gateway, ignore_backoff=True)
    assert second.synced == 1
    assert second.failed == 0
    assert len(gateway.rows('Production output')) == 1
    record.refresh_from_db()
    assert record.status == SheetSyncStatus.SYNCED
    assert record.sheet_row == 2
    output.quantity = Decimal('20')
    output.save()
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('production_output',)):
        third = run_sync(gateway=gateway)
    assert third.synced == 1
    assert len(gateway.rows('Production output')) == 1
    assert gateway.rows('Production output')[0][13] == '20.000'
    assert ProductionOutput.objects.get(pk=original_pk).quantity == Decimal('20.000')
    assert [call[0] for call in gateway.calls].count('append') == 1


@pytest.mark.django_db
def test_timeout_rate_limit_and_permanent_errors_keep_source_rows(factory, production_line):
    user = _personal_user(factory)
    output = _output(factory, production_line, user)
    before = ProductionOutput.objects.count()
    gateway = RecordingGateway()
    gateway.fail_next_append = True
    gateway.append_error = SheetsCallError('rate_limit', 'slow down', retry_after=45)
    started = timezone.now()
    with override_settings(
        GOOGLE_SHEETS_ENABLED=True,
        GOOGLE_SHEETS_DATASETS=('production_output',),
        GOOGLE_SHEETS_MAX_ATTEMPTS=2,
    ):
        limited = run_sync(gateway=gateway)
        assert limited.failed == 1
        record = SheetSyncRecord.objects.get()
        assert record.status == SheetSyncStatus.PENDING
        assert record.next_attempt_at >= started + timedelta(seconds=45)
        held = run_sync(gateway=gateway)
        assert held.synced == 0
        assert len(gateway.rows('Production output')) == 0
        record.next_attempt_at = timezone.now()
        record.save(update_fields=['next_attempt_at'])
        gateway.append_error = SheetsCallError('timeout', 'The Google Sheets request timed out.')
        gateway.fail_next_append = True
        timed_out = run_sync(gateway=gateway)
        assert timed_out.failed == 1
        record.refresh_from_db()
        assert record.status == SheetSyncStatus.FAILED
        assert record.attempt_count == 2
        ignored = run_sync(gateway=gateway)
        assert ignored.synced == 0
        record.refresh_from_db()
        assert record.status == SheetSyncStatus.FAILED
    assert ProductionOutput.objects.count() == before
    assert ProductionOutput.objects.get(pk=output.pk).quantity == Decimal('12.500')
    assert output.production_run.notes == PERSONAL_NOTE


@pytest.mark.django_db
def test_recovery_appends_once_after_a_timeout(factory, production_line):
    user = _personal_user(factory)
    output = _output(factory, production_line, user)
    gateway = RecordingGateway()
    gateway.fail_next_append = True
    gateway.append_error = SheetsCallError('timeout', 'The Google Sheets request timed out.')
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('production_output',)):
        failed = run_sync(gateway=gateway)
        assert failed.failed == 1
        assert ProductionOutput.objects.filter(pk=output.pk).count() == 1
        record = SheetSyncRecord.objects.get()
        record.next_attempt_at = timezone.now()
        record.save(update_fields=['next_attempt_at'])
        recovered = run_sync(gateway=gateway)
    assert recovered.outcome == 'ok'
    assert recovered.synced == 1
    assert len(gateway.rows('Production output')) == 1
    record.refresh_from_db()
    assert record.status == SheetSyncStatus.SYNCED


@pytest.mark.django_db
def test_plant_admin_sync_stays_inside_the_factory(factory, production_line):
    user = _personal_user(factory)
    home = _output(factory, production_line, user)
    other = Factory.objects.create(name='Other Factory', location='Sector B')
    other_line = production_line.__class__.objects.create(factory=other, name='Line 9', code='L9')
    other_run = ProductionRun.objects.create(
        factory=other,
        production_line=other_line,
        reference='PR-OTHER',
        status=ProductionRunStatus.IN_PROGRESS,
        started_at=datetime(2026, 10, 3, 8, 0, tzinfo=dt_timezone.utc),
    )
    ProductionOutput.objects.create(
        production_run=other_run,
        output_name='Other goods',
        quantity=Decimal('4'),
        recorded_at=datetime(2026, 10, 3, 9, 0, tzinfo=dt_timezone.utc),
    )
    gateway = RecordingGateway()
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('production_output',)):
        result = run_sync(gateway=gateway, factory_id=factory.pk)
    assert result.synced == 1
    keys = [row[0] for row in gateway.rows('Production output')]
    assert keys == [f'production_output:production.ProductionOutput:{home.pk}']
    assert SheetSyncRecord.objects.count() == 1


def _user(factory, role, username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@factoryops.local',
        password='Password123!',
        role=role,
        factory=factory,
    )


@pytest.mark.django_db
def test_only_administrators_can_open_or_run_sync(client, factory):
    url = reverse('reports:sheets_status')
    anonymous = client.get(url)
    assert anonymous.status_code == 302
    assert '/accounts/login/' in anonymous.url
    for role, username in (
        (Role.OPERATOR, 'floor-op'),
        (Role.QC, 'floor-qc'),
        (Role.SUPERVISOR, 'floor-sup'),
    ):
        client.force_login(_user(factory, role, username))
        assert client.get(url).status_code == 403
        assert client.post(url, {'action': 'sync'}).status_code == 403
        assert client.post(url, {'action': 'retry'}).status_code == 403
    admin = _user(factory, Role.ADMIN, 'floor-admin')
    client.force_login(admin)
    page = client.get(url)
    assert page.status_code == 200
    body = page.content.decode()
    assert 'Google Sheets integration is disabled.' in body
    assert 'No downtime records exist yet' in body
    assert 'No shift handover records exist yet' in body
    assert KEY_MATERIAL not in body
    posted = client.post(url, {'action': 'sync'}, follow=True)
    assert posted.status_code == 200
    assert 'disabled' in posted.content.decode().lower()
    assert SheetSyncRecord.objects.count() == 0


@pytest.mark.django_db
def test_manager_navigation_shows_sync_and_other_roles_do_not(client, factory):
    admin = _user(factory, Role.ADMIN, 'nav-admin')
    supervisor = _user(factory, Role.SUPERVISOR, 'nav-sup')
    url = reverse('reports:sheets_status')
    client.force_login(admin)
    manager = client.get(reverse('dashboard:manager'))
    assert manager.status_code == 200
    assert url in manager.content.decode()
    client.force_login(supervisor)
    supervised = client.get(reverse('dashboard:supervisor'))
    assert supervised.status_code == 200
    assert url not in supervised.content.decode()


@pytest.mark.django_db
def test_existing_dashboards_still_render_and_excel_export_is_unchanged(client, factory, production_line):
    user = _personal_user(factory)
    output = _output(factory, production_line, user)
    gateway = RecordingGateway()
    gateway.fail_next_append = True
    gateway.append_error = SheetsCallError('transient', 'offline')
    with override_settings(GOOGLE_SHEETS_ENABLED=True, GOOGLE_SHEETS_DATASETS=('production_output',)):
        failed = run_sync(gateway=gateway)
    assert failed.failed == 1
    assert ProductionOutput.objects.filter(pk=output.pk).exists()
    admin = _user(factory, Role.ADMIN, 'dash-admin')
    operator = _user(factory, Role.OPERATOR, 'dash-op')
    client.force_login(admin)
    assert client.get(reverse('dashboard:manager')).status_code == 200
    assert client.get(reverse('dashboard:executive')).status_code == 200
    assert client.get(reverse('dashboard:inventory')).status_code == 200
    client.force_login(operator)
    assert client.get(reverse('dashboard:operator')).status_code == 200
    assert client.get('/reports/export.xlsx').status_code == 404
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8').lower()
    assert 'openpyxl' not in requirements
    assert 'xlsxwriter' not in requirements


@pytest.mark.django_db
def test_credentials_are_not_logged_or_shown(client, factory, production_line, caplog, tmp_path):
    user = _personal_user(factory)
    _output(factory, production_line, user)
    secret_path = tmp_path / f'{KEY_MATERIAL}.json'
    secret_path.write_text(json.dumps({'private_key': KEY_MATERIAL, 'type': 'service_account'}), encoding='utf-8')
    gateway = RecordingGateway()
    gateway.fail_next_append = True
    gateway.store_before_append_error = True
    gateway.append_error = SheetsCallError(
        'transient',
        f'file {secret_path} -----BEGIN PRIVATE KEY-----\n{KEY_MATERIAL}\n-----END PRIVATE KEY----- ya29.{KEY_MATERIAL}',
    )
    caplog.set_level(logging.INFO, logger='apps.reports.sheets')
    with override_settings(
        GOOGLE_SHEETS_ENABLED=True,
        GOOGLE_SHEETS_SPREADSHEET_ID='sheet-123',
        GOOGLE_SHEETS_CREDENTIALS_FILE=str(secret_path),
        GOOGLE_SHEETS_DATASETS=('production_output',),
        GOOGLE_SHEETS_MAX_ATTEMPTS=1,
    ):
        result = run_sync(gateway=gateway)
        assert KEY_MATERIAL not in result.message
        assert str(secret_path) not in result.message
        admin = _user(factory, Role.ADMIN, 'secret-admin')
        client.force_login(admin)
        page = client.get(reverse('reports:sheets_status'))
    body = page.content.decode()
    log_text = caplog.text
    stored = SheetSyncRecord.objects.get().last_error
    for secret in (KEY_MATERIAL, 'ya29', 'BEGIN PRIVATE KEY', str(secret_path)):
        assert secret not in body
        assert secret not in log_text
        assert secret not in stored
        assert secret not in result.message


@pytest.mark.django_db
def test_misconfigured_sync_does_not_call_google_or_echo_the_path(tmp_path):
    secret_path = tmp_path / f'{KEY_MATERIAL}.json'
    secret_path.write_text(KEY_MATERIAL, encoding='utf-8')
    with override_settings(
        GOOGLE_SHEETS_ENABLED=True,
        GOOGLE_SHEETS_SPREADSHEET_ID='',
        GOOGLE_SHEETS_CREDENTIALS_FILE=str(secret_path),
    ):
        result = run_sync(gateway=None)
    assert result.outcome == 'misconfigured'
    assert KEY_MATERIAL not in result.message
    assert 'Spreadsheet ID is not configured.' in result.message


def test_service_account_errors_hide_the_key(tmp_path, monkeypatch):
    path = tmp_path / 'key.json'
    path.write_text('{"private_key": "%s", "type": "service_account"}' % KEY_MATERIAL, encoding='utf-8')
    with pytest.raises(SheetsCallError) as caught:
        load_service_account(str(path))
    assert caught.value.kind == 'config'
    assert KEY_MATERIAL not in str(caught.value)

    def explode(*args, **kwargs):
        raise RuntimeError(f'bad key {KEY_MATERIAL} -----BEGIN PRIVATE KEY----- {KEY_MATERIAL}')

    monkeypatch.setattr(
        'google.oauth2.service_account.Credentials.from_service_account_file',
        explode,
    )
    with pytest.raises(SheetsCallError) as wrapped:
        load_service_account(str(path))
    assert KEY_MATERIAL not in str(wrapped.value)


def test_http_errors_are_classified_without_the_response_body():
    class Response:
        status = 429
        reason = KEY_MATERIAL

        def get(self, key, default=None):
            if key == 'retry-after':
                return '12'
            return default

    from googleapiclient.errors import HttpError

    body = (
        '{"error": {"message": "%s -----BEGIN PRIVATE KEY----- abc -----END PRIVATE KEY-----"}}'
        % KEY_MATERIAL
    ).encode()
    failure = classify_transport_failure(HttpError(Response(), body))
    assert failure.kind == 'rate_limit'
    assert failure.retry_after == 12
    assert KEY_MATERIAL not in str(failure)
    assert 'BEGIN PRIVATE KEY' not in str(failure)

    class Denied(Response):
        status = 403

    denied = classify_transport_failure(HttpError(Denied(), b'{"error": {"message": "nope"}}'))
    assert denied.kind == 'permanent'
    assert classify_transport_failure(TimeoutError(KEY_MATERIAL)).kind == 'timeout'
    assert KEY_MATERIAL not in str(classify_transport_failure(TimeoutError(KEY_MATERIAL)))


def test_header_mismatch_does_not_rewrite_rows():
    class FakeApi:
        def __init__(self):
            self.sheets = [{'title': 'Production output', 'sheetId': 7}]
            self.header = ['Old header']
            self.writes = []
            self.formats = []

        def spreadsheet_sheets(self):
            return list(self.sheets)

        def add_sheet(self, title):
            raise AssertionError('should not add a tab')

        def read_values(self, range_name):
            return [self.header]

        def write_values(self, range_name, rows):
            self.writes.append(rows)

        def format_sheet(self, requests):
            self.formats.append(requests)

    api = FakeApi()
    gateway = GoogleSheetsGateway('sheet', 'unused.json', 30, api=api)
    with pytest.raises(SheetsCallError) as caught:
        gateway.prepare('Production output', PRODUCTION_OUTPUT_COLUMNS)
    assert caught.value.kind == 'permanent'
    assert api.writes == []
    assert api.formats == []


def test_new_tab_gets_the_header_and_formatting():
    class FakeApi:
        def __init__(self):
            self.sheets = []
            self.header = []
            self.formats = []

        def spreadsheet_sheets(self):
            return list(self.sheets)

        def add_sheet(self, title):
            self.sheets.append({'title': title, 'sheetId': 9})
            return 9

        def read_values(self, range_name):
            return [self.header] if self.header else []

        def write_values(self, range_name, rows):
            self.header = rows[0]

        def format_sheet(self, requests):
            self.formats = requests

        def update_rows(self, data):
            return None

        def append_rows(self, range_name, rows):
            return "'QC results'!A2:M2"

    api = FakeApi()
    gateway = GoogleSheetsGateway('sheet', 'unused.json', 30, api=api)
    gateway.prepare('QC results', QC_RESULT_COLUMNS)
    assert api.header == [column.header for column in QC_RESULT_COLUMNS]
    assert api.formats[0]['updateSheetProperties']['properties']['gridProperties']['frozenRowCount'] == 1
    assert api.formats[1]['repeatCell']['cell']['userEnteredFormat']['textFormat']['bold'] is True
    numbers = gateway.append_rows('QC results', [['qc_results:production.QCVerification:1']])
    assert numbers == [2]


def test_windows_sheet_scripts_match_the_factory_pc_contract():
    windows = ROOT / 'deploy' / 'windows'
    register = (windows / 'Register-FactoryOpsSheetsSync.ps1').read_text(encoding='utf-8')
    runner = (windows / 'Run-FactoryOpsSheetsSync.ps1').read_text(encoding='utf-8')
    common = (windows / 'FactoryOps.Common.ps1').read_text(encoding='utf-8')
    uninstall = (windows / 'Uninstall-FactoryOps.ps1').read_text(encoding='utf-8')
    status = (windows / 'Get-FactoryOpsStatus.ps1').read_text(encoding='utf-8')
    for text in (register, runner, common, uninstall, status):
        assert '&&' not in text
        assert '??' not in text
        assert 'private_key' not in text
        assert KEY_MATERIAL not in text
    assert 'sync_google_sheets' in runner
    assert 'DJANGO_SETTINGS_MODULE' in runner
    assert 'config.settings.production' in runner
    assert 'not print .env' in runner
    assert 'FactoryOpsSheetsSync' in common
    assert 'FactoryOpsSheetsTask' in uninstall
    assert 'does not delete the database' in uninstall
    assert 'SupportsShouldProcess' in register
    assert 'IgnoreNew' in register
    assert 'SYSTEM' in register
    assert 'IntervalMinutes -lt 15' in register
    assert 'FactoryOpsSheetsSync is not registered' in status
    example = (ROOT / '.env.example').read_text(encoding='utf-8')
    production = (ROOT / '.env.production.example').read_text(encoding='utf-8')
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for text in (example, production):
        assert 'GOOGLE_SHEETS_ENABLED=False' in text
        assert 'private_key' not in text
    assert 'secrets/' in gitignore
    assert 'service-account' in gitignore


@pytest.mark.django_db
def test_command_stays_quiet_when_disabled_and_fails_closed_when_misconfigured(tmp_path):
    stdout = StringIO()
    call_command('sync_google_sheets', stdout=stdout)
    assert 'disabled' in stdout.getvalue().lower()

    secret_path = tmp_path / f'{KEY_MATERIAL}.json'
    secret_path.write_text(KEY_MATERIAL, encoding='utf-8')
    with override_settings(
        GOOGLE_SHEETS_ENABLED=True,
        GOOGLE_SHEETS_SPREADSHEET_ID='',
        GOOGLE_SHEETS_CREDENTIALS_FILE=str(secret_path),
    ):
        with pytest.raises(CommandError) as caught:
            call_command('sync_google_sheets', stdout=StringIO())
    assert KEY_MATERIAL not in str(caught.value)
    assert 'Spreadsheet ID is not configured.' in str(caught.value)


@pytest.mark.django_db
def test_command_retry_flag_resets_backoff(monkeypatch):
    seen = {}

    def fake_run_sync(**kwargs):
        seen.update(kwargs)
        return type('Result', (), {
            'outcome': 'ok',
            'message': 'Synced 0. Failed 0. Pending 0.',
        })()

    monkeypatch.setattr(
        'apps.reports.management.commands.sync_google_sheets.run_sync',
        fake_run_sync,
    )
    call_command('sync_google_sheets', '--retry', stdout=StringIO())
    assert seen['ignore_backoff'] is True
    assert seen['trigger'] == 'command'


@pytest.mark.django_db
def test_a_second_sync_is_rejected_while_the_lock_is_held():
    from apps.reports.models import SheetSyncLock
    SheetSyncLock.objects.create(name='google-sheets', locked_until=timezone.now() + timedelta(minutes=5))
    result = run_sync(gateway=BoomGateway())
    assert result.outcome == 'busy'
    assert SheetSyncRecord.objects.count() == 0


@pytest.mark.django_db
def test_busy_windows_style_credentials_path_is_not_echoed():
    windows_path = r'C:\FactoryOps\secrets\SUPERSECRETKEY.json'
    with override_settings(
        GOOGLE_SHEETS_ENABLED=True,
        GOOGLE_SHEETS_SPREADSHEET_ID='sheet-123',
        GOOGLE_SHEETS_CREDENTIALS_FILE=windows_path,
    ):
        result = run_sync()
    assert result.outcome == 'misconfigured'
    assert 'Credentials file is not configured.' in result.message
    assert 'SUPERSECRETKEY' not in result.message
    assert 'FactoryOps' not in result.message
