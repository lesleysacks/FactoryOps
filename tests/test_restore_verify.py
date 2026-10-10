"""Backup manifests, checksums, and restore verification on disposable copies."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from scripts.backup_factoryops import (
    create_backup,
    default_backup_root,
    main as backup_main,
    setup_django,
    validate_backup,
)
from scripts.restore_factoryops import main as restore_main, restore_backup
from scripts.verify_restore import main as verify_main, verify_restore


def _live_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute('create table pads (n integer)')
    connection.execute('insert into pads values (7)')
    connection.commit()
    connection.close()


def _backup(tmp_path, media_files=None, secret=None):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    media = app / 'media'
    if media_files:
        for relative, payload in media_files.items():
            target = media / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    if secret:
        media.mkdir(parents=True, exist_ok=True)
        (media / '.env').write_text(secret, encoding='utf-8')
    before = database.read_bytes()
    result = create_backup(
        database,
        media,
        tmp_path / 'backups',
        14,
        application_root=app,
    )
    assert database.read_bytes() == before
    return database, result


def _manifest(bundle):
    return json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))


def test_backup_writes_checksums_and_keeps_relative_media_paths(tmp_path):
    payload = b'jpeg-bytes'
    database, result = _backup(
        tmp_path,
        {'qc/line-1/photo.jpg': payload},
        secret='SECRET_KEY=super-secret-value',
    )
    bundle = result['bundle']
    assert result['media_status'] == 'copied'
    assert 'MEDIA copied' in result['media_message']
    assert (bundle / 'media' / 'qc' / 'line-1' / 'photo.jpg').read_bytes() == payload
    assert not (bundle / 'media' / '.env').exists()
    manifest = _manifest(bundle)
    assert manifest['database_engine'] == 'django.db.backends.sqlite3'
    assert manifest['database_name'] == 'db.sqlite3'
    assert manifest['integrity_check'] == 'ok'
    assert manifest['created_at']
    photo = next(item for item in manifest['files'] if item['path'] == 'media/qc/line-1/photo.jpg')
    assert photo['size'] == len(payload)
    assert photo['sha256'] == hashlib.sha256(payload).hexdigest()
    assert 'super-secret-value' not in (bundle / 'manifest.json').read_text(encoding='utf-8')
    snapshot = sqlite3.connect(f'file:{bundle / "db.sqlite3"}?mode=ro', uri=True)
    try:
        assert snapshot.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert snapshot.execute('select n from pads').fetchone()[0] == 7
    finally:
        snapshot.close()
    live = sqlite3.connect(database)
    try:
        assert live.execute("select name from sqlite_master where name='django_migrations'").fetchone() is None
    finally:
        live.close()


def test_second_backup_in_the_same_second_does_not_overwrite(tmp_path):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    moment = datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc)
    first = create_backup(database, app / 'media', tmp_path / 'backups', 14, application_root=app, now=moment)
    original = (first['bundle'] / 'db.sqlite3').read_bytes()
    second = create_backup(database, app / 'media', tmp_path / 'backups', 14, application_root=app, now=moment)
    assert first['bundle'] != second['bundle']
    assert first['bundle'].is_dir()
    assert (first['bundle'] / 'db.sqlite3').read_bytes() == original
    assert (second['bundle'] / 'db.sqlite3').is_file()


def test_missing_database_and_corrupt_sqlite_leave_no_backup(tmp_path):
    app = tmp_path / 'app'
    destination = tmp_path / 'backups'
    with pytest.raises(FileNotFoundError):
        create_backup(app / 'missing.sqlite3', app / 'media', destination, 14, application_root=app)
    assert list(destination.rglob('db.sqlite3')) == []

    database = app / 'db.sqlite3'
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b'this is not a sqlite database')
    with pytest.raises(RuntimeError):
        create_backup(database, app / 'media', destination, 14, application_root=app)
    assert list(destination.rglob('db.sqlite3')) == []


def test_backup_rejects_a_non_sqlite_engine_and_a_destination_inside_media(tmp_path):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    photos = tmp_path / 'photos'
    photos.mkdir()
    before = database.read_bytes()
    with pytest.raises(RuntimeError, match='SQLite'):
        create_backup(
            database,
            photos,
            tmp_path / 'backups',
            14,
            application_root=app,
            database_engine='django.db.backends.postgresql',
        )
    with pytest.raises(ValueError, match='media directory'):
        create_backup(database, photos, photos / 'backups', 14, application_root=app)
    assert database.read_bytes() == before
    assert list(photos.rglob('db.sqlite3')) == []


def test_absent_and_empty_media_are_reported(tmp_path):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    absent = create_backup(database, app / 'media', tmp_path / 'backups-a', 14, application_root=app)
    assert absent['media_status'] == 'absent'
    assert 'MEDIA absent' in absent['media_message']
    assert _manifest(absent['bundle'])['media_status'] == 'absent'
    assert not (absent['bundle'] / 'media').exists()

    (app / 'media').mkdir()
    empty = create_backup(database, app / 'media', tmp_path / 'backups-b', 14, application_root=app)
    assert empty['media_status'] == 'empty'
    assert 'MEDIA empty' in empty['media_message']
    names = [item['path'] for item in _manifest(empty['bundle'])['files']]
    assert names == ['db.sqlite3']


def test_checksum_mismatch_and_corrupt_snapshot_fail_validation(tmp_path):
    database, result = _backup(tmp_path, {'qc/photo.jpg': b'jpeg'})
    bundle = result['bundle']
    photo = bundle / 'media' / 'qc' / 'photo.jpg'
    photo.write_bytes(b'XXXX')
    with pytest.raises(ValueError, match='checksum mismatch'):
        validate_backup(bundle)

    photo.write_bytes(b'jpeg')
    manifest = _manifest(bundle)
    snapshot = bundle / 'db.sqlite3'
    snapshot.write_bytes(b'not-a-database')
    for entry in manifest['files']:
        path = bundle / entry['path']
        blob = path.read_bytes()
        entry['size'] = len(blob)
        entry['sha256'] = hashlib.sha256(blob).hexdigest()
    (bundle / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(RuntimeError, match='integrity'):
        validate_backup(bundle)
    assert database.is_file()


def test_restore_refuses_a_backup_with_missing_media(tmp_path, capsys):
    database, result = _backup(tmp_path, {'qc/photo.jpg': b'jpeg'})
    bundle = result['bundle']
    (bundle / 'media' / 'qc' / 'photo.jpg').unlink()
    separate = tmp_path / 'restored'
    before = database.read_bytes()
    with pytest.raises(FileNotFoundError, match='missing'):
        restore_backup(bundle, separate, live_database=database)
    assert not separate.exists()
    code = restore_main(
        ['--backup', str(bundle), '--destination', str(separate), '--live-database', str(database), '--confirm']
    )
    captured = capsys.readouterr()
    assert code == 1
    assert 'RESTORE FAILED' in captured.err
    assert 'RESTORE OK' not in captured.out
    assert not separate.exists()
    assert database.read_bytes() == before


def test_verify_refuses_the_live_database_path(tmp_path):
    database, result = _backup(tmp_path, {'qc/photo.jpg': b'jpeg'})
    before = database.read_bytes()
    mtime = database.stat().st_mtime_ns
    with pytest.raises(ValueError, match='live database'):
        verify_restore(
            result['bundle'],
            destination=database.parent,
            live_database=database,
            exercise_django=True,
        )
    with pytest.raises(ValueError, match='live database'):
        verify_restore(
            result['bundle'],
            destination=database,
            live_database=database,
            exercise_django=True,
        )
    assert database.read_bytes() == before
    assert database.stat().st_mtime_ns == mtime
    assert (database.parent / 'media' / 'qc' / 'photo.jpg').read_bytes() == b'jpeg'


def test_verify_refuses_the_repository_database(tmp_path, settings):
    project_db = Path(settings.BASE_DIR) / 'db.sqlite3'
    existed = project_db.exists()
    before = project_db.read_bytes() if existed else None
    mtime = project_db.stat().st_mtime_ns if existed else None
    _database, result = _backup(tmp_path)
    with pytest.raises(ValueError, match='live database'):
        verify_restore(
            result['bundle'],
            destination=project_db.parent,
            live_database=project_db,
            exercise_django=True,
        )
    if existed:
        assert project_db.read_bytes() == before
        assert project_db.stat().st_mtime_ns == mtime
    else:
        assert not project_db.exists()


def test_verify_restore_migrates_only_the_disposable_copy(tmp_path):
    database, result = _backup(tmp_path, {'qc/photo.jpg': b'jpeg'})
    before = database.read_bytes()
    separate = tmp_path / 'rehearsal'
    outcome = verify_restore(
        result['bundle'],
        destination=separate,
        live_database=database,
    )
    assert outcome['kept'] is True
    assert 'VERIFY' not in outcome['messages'][-1]
    assert (separate / 'media' / 'qc' / 'photo.jpg').read_bytes() == b'jpeg'
    restored = sqlite3.connect(separate / 'db.sqlite3')
    live = sqlite3.connect(database)
    try:
        assert restored.execute('select count(*) from django_migrations').fetchone()[0] > 0
        assert restored.execute('select n from pads').fetchone()[0] == 7
        assert live.execute("select name from sqlite_master where name='django_migrations'").fetchone() is None
        assert live.execute('select n from pads').fetchone()[0] == 7
    finally:
        restored.close()
        live.close()
    assert database.read_bytes() == before


def test_management_commands_use_configured_paths_and_refuse_the_live_file(tmp_path, settings):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    media = app / 'media' / 'qc'
    media.mkdir(parents=True)
    (media / 'photo.jpg').write_bytes(b'jpeg')
    settings.DATABASES['default']['NAME'] = database
    settings.MEDIA_ROOT = app / 'media'
    before = database.read_bytes()
    destination = tmp_path / 'backups'
    call_command('backup_factoryops', destination=str(destination))
    bundles = list(destination.iterdir())
    assert len(bundles) == 1
    manifest = _manifest(bundles[0])
    assert any(item['path'] == 'media/qc/photo.jpg' for item in manifest['files'])
    assert database.read_bytes() == before

    with pytest.raises(CommandError, match='VERIFY FAILED'):
        call_command('verify_restore', backup=str(bundles[0]), destination=str(database.parent))
    assert database.read_bytes() == before

    rehearsal = tmp_path / 'rehearsal'
    call_command('verify_restore', backup=str(bundles[0]), destination=str(rehearsal))
    assert (rehearsal / 'db.sqlite3').is_file()
    assert (rehearsal / 'media' / 'qc' / 'photo.jpg').read_bytes() == b'jpeg'
    assert database.read_bytes() == before


def test_cli_discovers_settings_and_does_not_print_secrets(tmp_path, settings, capsys, monkeypatch):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    media = app / 'media'
    media.mkdir()
    (media / '.env').write_text('SECRET_KEY=super-secret-value', encoding='utf-8')
    (media / 'qc').mkdir()
    (media / 'qc' / 'photo.jpg').write_bytes(b'jpeg')
    settings.DATABASES['default']['NAME'] = database
    settings.MEDIA_ROOT = media

    def explode():
        raise AssertionError('explicit paths must not bootstrap Django')

    monkeypatch.setattr('scripts.backup_factoryops.setup_django', explode)
    explicit = backup_main(
        [
            '--database', str(database),
            '--media', str(media),
            '--destination', str(tmp_path / 'explicit'),
            '--application-root', str(app),
        ]
    )
    assert explicit == 0
    monkeypatch.setattr('scripts.backup_factoryops.setup_django', setup_django)

    code = backup_main(['--destination', str(tmp_path / 'from-settings')])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert 'BACKUP OK' in captured.out
    assert 'MEDIA copied' in captured.out
    assert 'super-secret-value' not in captured.out
    assert 'super-secret-value' not in captured.err


def test_default_backup_root_honours_the_environment(monkeypatch, tmp_path):
    monkeypatch.delenv('FACTORYOPS_BACKUP_DIR', raising=False)
    assert default_backup_root() == Path.home() / 'FactoryOpsBackups'
    monkeypatch.setenv('FACTORYOPS_BACKUP_DIR', str(tmp_path / 'chosen'))
    assert default_backup_root() == tmp_path / 'chosen'


def test_verify_cli_reports_failure_for_a_missing_backup(tmp_path, capsys):
    code = verify_main(
        [
            '--backup', str(tmp_path / 'missing'),
            '--destination', str(tmp_path / 'out'),
            '--live-database', str(tmp_path / 'live.sqlite3'),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert 'VERIFY FAILED' in captured.err
    assert 'VERIFY OK' not in captured.out
    assert not (tmp_path / 'out').exists()
