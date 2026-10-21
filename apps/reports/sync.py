"""Deliver approved datasets to Google Sheets without touching source rows.

Capture requests do not call this module. A management command or an
administrator action scans source tables, updates a local outbox, and pushes
a bounded batch. A database lock stops two pushes from appending the same
source key. If the network fails, the source row and the outbox row remain.
"""

import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.reports.datasets import all_datasets, dataset_by_key
from apps.reports.errors import SheetsCallError
from apps.reports.models import SheetSyncLock, SheetSyncRecord, SheetSyncRun, SheetSyncStatus
from apps.reports.redaction import redact

logger = logging.getLogger('apps.reports.sheets')

LOCK_NAME = 'google-sheets'
LOCK_MINUTES = 15

PROBLEMS = {
    'disabled': 'Google Sheets integration is disabled.',
    'missing_spreadsheet_id': 'Spreadsheet ID is not configured.',
    'missing_credentials_file': 'Credentials file is not configured.',
}


class SyncResult:
    def __init__(self, outcome, message, synced=0, failed=0, pending=0):
        self.outcome = outcome
        self.message = message
        self.synced = synced
        self.failed = failed
        self.pending = pending


def sheets_problems():
    """Why the integration cannot call Google. Empty when it is ready."""
    if not settings.GOOGLE_SHEETS_ENABLED:
        return ('disabled',)
    problems = []
    if not settings.GOOGLE_SHEETS_SPREADSHEET_ID:
        problems.append('missing_spreadsheet_id')
    credentials = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
    if not credentials or not _credentials_file_exists(credentials):
        problems.append('missing_credentials_file')
    return tuple(problems)


def selected_datasets():
    configured = settings.GOOGLE_SHEETS_DATASETS
    if not configured:
        return [dataset for dataset in all_datasets() if dataset.available]
    chosen = []
    for key in configured:
        dataset = dataset_by_key(key)
        if dataset is not None:
            chosen.append(dataset)
    return chosen


def unknown_dataset_keys():
    known = {dataset.key for dataset in all_datasets()}
    return [key for key in settings.GOOGLE_SHEETS_DATASETS if key not in known]


def run_sync(*, gateway=None, factory_id=None, trigger='command', actor_id=None, ignore_backoff=False):
    """Scan, enqueue, and push. Returns without calling Google when disabled."""
    now = timezone.now()
    if not _acquire_lock(now):
        message = 'A sheet sync is already running.'
        logger.info('sheet sync skipped outcome=busy')
        return SyncResult('busy', message)

    run = None
    try:
        problems = sheets_problems()
        if 'disabled' in problems:
            message = PROBLEMS['disabled']
            logger.info('sheet sync skipped outcome=disabled')
            return SyncResult('disabled', message)
        if gateway is None and problems:
            message = ' '.join(PROBLEMS[item] for item in problems)
            _record_run(trigger, actor_id, 'misconfigured', message, 0, 0, _pending_count(factory_id), now)
            logger.warning('sheet sync skipped outcome=misconfigured')
            return SyncResult('misconfigured', message)
        if gateway is None:
            from apps.reports.google_client import build_google_gateway
            try:
                gateway = build_google_gateway()
            except SheetsCallError as exc:
                message = _safe(str(exc))
                _record_run(trigger, actor_id, 'misconfigured', message, 0, 0, _pending_count(factory_id), now)
                logger.warning('sheet sync skipped outcome=misconfigured detail=%s', message)
                return SyncResult('misconfigured', message)

        run = SheetSyncRun.objects.create(
            started_at=now,
            trigger=trigger,
            actor_id=actor_id,
            outcome='running',
            message='',
        )
        synced = 0
        failed = 0
        notes = []
        remaining = settings.GOOGLE_SHEETS_BATCH_SIZE
        for dataset in selected_datasets():
            if not dataset.available:
                notes.append(dataset.title)
                continue
            _refresh_outbox(dataset, factory_id, now)
            if ignore_backoff:
                _release_backoff(dataset.key, factory_id, now)
            if remaining <= 0:
                continue
            pushed, broken = _push_dataset(dataset, gateway, factory_id, now, remaining)
            synced += pushed
            failed += broken
            remaining -= pushed + broken
        pending = _pending_count(factory_id)
        message = _summary(synced, failed, pending, notes)
        if failed and synced:
            outcome = 'partial'
        elif failed:
            outcome = 'failed'
        else:
            outcome = 'ok'
        _finish_run(run, outcome, message, synced, failed, pending)
        logger.info(
            'sheet sync outcome=%s synced=%s failed=%s pending=%s',
            outcome, synced, failed, pending,
        )
        return SyncResult(outcome, message, synced, failed, pending)
    except Exception as exc:
        message = _safe(str(exc)) or 'The sheet sync failed.'
        logger.warning('sheet sync outcome=failed detail=%s', message)
        if run is not None and run.finished_at is None:
            _finish_run(run, 'failed', message, 0, 0, _pending_count(factory_id))
        return SyncResult('failed', message, 0, 0, _pending_count(factory_id))
    finally:
        _release_lock()


def status_snapshot(factory_id=None):
    """Database and settings only. Does not contact Google."""
    problems = sheets_problems()
    datasets = []
    for dataset in all_datasets():
        records = SheetSyncRecord.objects.filter(dataset=dataset.key)
        if factory_id is not None:
            records = records.filter(factory_id=factory_id)
        last_error = records.exclude(last_error='').order_by('-updated_at').values_list(
            'last_error', flat=True,
        ).first()
        datasets.append({
            'key': dataset.key,
            'title': dataset.title,
            'available': dataset.available,
            'reason': dataset.unavailable_reason,
            'pending': records.filter(status=SheetSyncStatus.PENDING).count(),
            'synced': records.filter(status=SheetSyncStatus.SYNCED).count(),
            'failed': records.filter(status=SheetSyncStatus.FAILED).count(),
            'last_error': _safe(last_error or ''),
        })
    runs = [
        {
            'started_at': item.started_at,
            'outcome': item.outcome,
            'message': _safe(item.message),
            'synced_count': item.synced_count,
            'failed_count': item.failed_count,
            'pending_count': item.pending_count,
            'trigger': item.trigger,
        }
        for item in SheetSyncRun.objects.order_by('-started_at')[:8]
    ]
    configured = bool(settings.GOOGLE_SHEETS_SPREADSHEET_ID)
    return {
        'enabled': settings.GOOGLE_SHEETS_ENABLED,
        'ready': not problems,
        'problems': [PROBLEMS[item] for item in problems],
        'spreadsheet_configured': configured,
        'spreadsheet_id': settings.GOOGLE_SHEETS_SPREADSHEET_ID if configured else '',
        'datasets': datasets,
        'runs': runs,
        'factory_scoped': factory_id is not None,
        'unknown_datasets': unknown_dataset_keys(),
    }


def _credentials_file_exists(path):
    from pathlib import Path
    try:
        return Path(path).is_file()
    except OSError:
        return False


def _safe(value):
    """Redact secrets and the credentials path, then fit the sync record fields."""
    text = redact(value, limit=4000)
    path = settings.GOOGLE_SHEETS_CREDENTIALS_FILE or ''
    if path:
        text = text.replace(path, '[redacted]')
    if len(text) > 500:
        return text[:499] + '…'
    return text


def _content_hash(cells):
    payload = json.dumps(list(cells), ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _refresh_outbox(dataset, factory_id, now):
    for row in dataset.collect(factory_id):
        digest = _content_hash(row.cells)
        record = SheetSyncRecord.objects.filter(
            dataset=dataset.key,
            source_model=row.source_model,
            source_id=row.source_id,
        ).first()
        if record is None:
            SheetSyncRecord.objects.create(
                dataset=dataset.key,
                source_model=row.source_model,
                source_id=row.source_id,
                source_key=row.source_key,
                factory_id=row.factory_id,
                payload=list(row.cells),
                payload_hash=digest,
                status=SheetSyncStatus.PENDING,
                next_attempt_at=now,
            )
            continue
        fields = []
        if record.payload_hash != digest:
            record.payload = list(row.cells)
            record.payload_hash = digest
            record.status = SheetSyncStatus.PENDING
            record.attempt_count = 0
            record.next_attempt_at = now
            record.last_error = ''
            fields.extend([
                'payload', 'payload_hash', 'status', 'attempt_count',
                'next_attempt_at', 'last_error',
            ])
        if record.factory_id != row.factory_id:
            record.factory_id = row.factory_id
            fields.append('factory')
        if record.source_key != row.source_key:
            record.source_key = row.source_key
            fields.append('source_key')
        if fields:
            record.save(update_fields=fields)


def _release_backoff(dataset_key, factory_id, now):
    records = SheetSyncRecord.objects.filter(dataset=dataset_key).filter(
        Q(status=SheetSyncStatus.PENDING) | Q(status=SheetSyncStatus.FAILED)
    )
    if factory_id is not None:
        records = records.filter(factory_id=factory_id)
    records.update(
        status=SheetSyncStatus.PENDING,
        attempt_count=0,
        next_attempt_at=now,
    )


def _due_records(dataset_key, factory_id, now, limit):
    records = SheetSyncRecord.objects.filter(
        dataset=dataset_key,
        status=SheetSyncStatus.PENDING,
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
    if factory_id is not None:
        records = records.filter(factory_id=factory_id)
    return list(records.order_by('id')[:limit])


def _push_dataset(dataset, gateway, factory_id, now, limit):
    records = _due_records(dataset.key, factory_id, now, limit)
    if not records:
        return 0, 0
    try:
        gateway.prepare(dataset.title, dataset.columns)
        existing = gateway.source_key_rows(dataset.title)
    except SheetsCallError as exc:
        _stamp_failure(records, exc, now)
        return 0, len(records)
    updates = []
    appends = []
    for record in records:
        cells = list(record.payload)
        row_number = existing.get(record.source_key)
        if row_number:
            updates.append((record, row_number, cells))
        else:
            appends.append((record, cells))
    synced = 0
    failed = 0
    if updates:
        try:
            gateway.write_rows(dataset.title, [(row_number, cells) for _, row_number, cells in updates])
        except SheetsCallError as exc:
            _stamp_failure([record for record, _, _ in updates], exc, now)
            failed += len(updates)
            updates = []
        else:
            for record, row_number, _cells in updates:
                _stamp_success(record, row_number, now)
                synced += 1
    if appends:
        try:
            gateway.append_rows(dataset.title, [cells for _, cells in appends])
            confirmed = gateway.source_key_rows(dataset.title)
        except SheetsCallError as exc:
            _stamp_failure([record for record, _ in appends], exc, now)
            failed += len(appends)
        else:
            missing = []
            for record, _cells in appends:
                row_number = confirmed.get(record.source_key)
                if row_number:
                    _stamp_success(record, row_number, now)
                    synced += 1
                else:
                    missing.append(record)
            if missing:
                _stamp_failure(missing, SheetsCallError('transient', 'Appended row was not found.'), now)
                failed += len(missing)
    return synced, failed


def _retry_delay(attempt, retry_after):
    if retry_after is not None:
        delay = float(retry_after)
    else:
        delay = float(settings.GOOGLE_SHEETS_BACKOFF_SECONDS) * (2 ** max(attempt - 1, 0))
    return min(max(delay, 0), 3600)


def _stamp_failure(records, exc, now):
    message = _safe(str(exc))
    for record in records:
        attempt = record.attempt_count + 1
        record.attempt_count = attempt
        record.last_error = message
        if attempt >= settings.GOOGLE_SHEETS_MAX_ATTEMPTS:
            record.status = SheetSyncStatus.FAILED
            record.next_attempt_at = None
        else:
            record.status = SheetSyncStatus.PENDING
            record.next_attempt_at = now + timedelta(seconds=_retry_delay(attempt, exc.retry_after))
        record.save(update_fields=['attempt_count', 'last_error', 'status', 'next_attempt_at'])
        logger.warning(
            'sheet sync delayed source_key=%s kind=%s attempts=%s detail=%s',
            record.source_key, exc.kind, attempt, message,
        )


def _stamp_success(record, row_number, now):
    record.status = SheetSyncStatus.SYNCED
    record.sheet_row = row_number
    record.synced_at = now
    record.last_error = ''
    record.save(update_fields=['status', 'sheet_row', 'synced_at', 'last_error'])


def _pending_count(factory_id):
    records = SheetSyncRecord.objects.filter(status=SheetSyncStatus.PENDING)
    if factory_id is not None:
        records = records.filter(factory_id=factory_id)
    return records.count()


def _summary(synced, failed, pending, skipped_titles):
    message = f'Synced {synced}. Failed {failed}. Pending {pending}.'
    if skipped_titles:
        message += ' Not synced because there is no source model: ' + ', '.join(skipped_titles) + '.'
    unknown = unknown_dataset_keys()
    if unknown:
        message += ' Ignored unknown datasets: ' + ', '.join(unknown) + '.'
    return _safe(message)


def _record_run(trigger, actor_id, outcome, message, synced, failed, pending, now):
    SheetSyncRun.objects.create(
        started_at=now,
        finished_at=timezone.now(),
        trigger=trigger,
        actor_id=actor_id,
        outcome=outcome,
        message=_safe(message),
        synced_count=synced,
        failed_count=failed,
        pending_count=pending,
    )


def _finish_run(run, outcome, message, synced, failed, pending):
    run.finished_at = timezone.now()
    run.outcome = outcome
    run.message = _safe(message)
    run.synced_count = synced
    run.failed_count = failed
    run.pending_count = pending
    run.save(update_fields=[
        'finished_at', 'outcome', 'message', 'synced_count', 'failed_count', 'pending_count',
    ])


def _acquire_lock(now):
    SheetSyncLock.objects.get_or_create(name=LOCK_NAME)
    with transaction.atomic():
        lock = SheetSyncLock.objects.select_for_update().get(name=LOCK_NAME)
        if lock.locked_until and lock.locked_until > now:
            return False
        lock.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        lock.save(update_fields=['locked_until'])
        return True


def _release_lock():
    SheetSyncLock.objects.filter(name=LOCK_NAME).update(locked_until=None)
