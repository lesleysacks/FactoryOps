"""Backup and restore behaviour for the SQLite factory database."""

import sqlite3
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from config.ops.backup import create_backup, redact_env_text, restore_backup, verify_backup
from config.ops.envfile import apply_lan_address, render_production_env


def _make_db(path: Path, marker: str) -> None:
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE events (marker TEXT)')
    connection.execute('INSERT INTO events (marker) VALUES (?)', (marker,))
    connection.commit()
    connection.close()


def _marker(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute('SELECT marker FROM events').fetchone()
    finally:
        connection.close()
    return row[0]


def _env(path: Path) -> None:
    path.write_text(
        'SECRET_KEY=' + ('s' * 60) + '\nDEBUG=False\nALLOWED_HOSTS=localhost\n',
        encoding='utf-8',
    )


def test_redact_env_removes_secret_and_keeps_hosts():
    text = 'SECRET_KEY=real-secret\nDEBUG=False\nALLOWED_HOSTS=localhost\n'
    redacted = redact_env_text(text)
    assert 'SECRET_KEY=REDACTED' in redacted
    assert 'real-secret' not in redacted
    assert 'ALLOWED_HOSTS=localhost' in redacted


def test_backup_is_consistent_and_verified(tmp_path):
    database = tmp_path / 'live.sqlite3'
    media = tmp_path / 'media'
    media.mkdir()
    (media / 'photo.txt').write_text('qc-photo', encoding='utf-8')
    env_file = tmp_path / 'factoryops.env'
    _make_db(database, 'shift-a')
    _env(env_file)
    log_path = tmp_path / 'logs' / 'backup.log'
    holder = sqlite3.connect(database)
    try:
        result = create_backup(
            database_path=database,
            media_root=media,
            env_file=env_file,
            backup_root=tmp_path / 'backups',
            retention=14,
            log_path=log_path,
        )
    finally:
        holder.close()
    assert result.verified is True
    assert result.path is not None
    assert _marker(database) == 'shift-a'
    assert _marker(result.path / 'db.sqlite3') == 'shift-a'
    assert (result.path / 'media' / 'photo.txt').read_text(encoding='utf-8') == 'qc-photo'
    redacted = (result.path / 'factoryops.env.redacted').read_text(encoding='utf-8')
    assert 'SECRET_KEY=REDACTED' in redacted
    assert 's' * 60 not in redacted
    ok, detail = verify_backup(result.path)
    assert ok, detail
    assert 'Backup verified' in log_path.read_text(encoding='utf-8')


def test_failed_backup_does_not_remove_previous_verified_backup(tmp_path):
    database = tmp_path / 'live.sqlite3'
    _make_db(database, 'kept')
    backup_root = tmp_path / 'backups'
    log_path = tmp_path / 'backup.log'
    first = create_backup(
        database_path=database,
        media_root=tmp_path / 'missing-media',
        env_file=None,
        backup_root=backup_root,
        retention=14,
        log_path=log_path,
    )
    assert first.verified
    bad = tmp_path / 'not-a-database.txt'
    bad.write_text('this is not sqlite', encoding='utf-8')
    failed = create_backup(
        database_path=bad,
        media_root=tmp_path / 'missing-media',
        env_file=None,
        backup_root=backup_root,
        retention=1,
        log_path=log_path,
    )
    assert failed.verified is False
    assert first.path.is_dir()
    assert 'was not verified' in log_path.read_text(encoding='utf-8')
    assert _marker(database) == 'kept'


def test_retention_keeps_verified_backups_only_after_success(tmp_path):
    database = tmp_path / 'live.sqlite3'
    _make_db(database, 'row')
    backup_root = tmp_path / 'backups'
    created = []
    for _ in range(3):
        result = create_backup(
            database_path=database,
            media_root=tmp_path / 'media',
            env_file=None,
            backup_root=backup_root,
            retention=2,
            log_path=tmp_path / 'backup.log',
        )
        assert result.verified
        created.append(result.path)
    remaining = sorted(path.name for path in backup_root.iterdir())
    assert created[0].name not in remaining
    assert created[1].name in remaining
    assert created[2].name in remaining


def test_restore_to_scratch_leaves_live_database_untouched(tmp_path):
    live = tmp_path / 'data' / 'db.sqlite3'
    live.parent.mkdir()
    _make_db(live, 'live-row')
    media = tmp_path / 'data' / 'media'
    media.mkdir()
    (media / 'keep.txt').write_text('original', encoding='utf-8')
    backup = create_backup(
        database_path=live,
        media_root=media,
        env_file=None,
        backup_root=tmp_path / 'backups',
        retention=5,
        log_path=None,
    )
    connection = sqlite3.connect(live)
    connection.execute("UPDATE events SET marker = 'changed-after-backup'")
    connection.commit()
    connection.close()
    scratch = tmp_path / 'scratch'
    restored = restore_backup(
        backup_dir=backup.path,
        target_dir=scratch,
        live_database_path=live,
        live_media_root=media,
        replace_live=False,
    )
    assert restored.verified
    assert _marker(scratch / 'db.sqlite3') == 'live-row'
    assert _marker(live) == 'changed-after-backup'
    assert (media / 'keep.txt').read_text(encoding='utf-8') == 'original'


def test_restore_refuses_to_overwrite_live_database(tmp_path):
    live = tmp_path / 'data' / 'db.sqlite3'
    live.parent.mkdir()
    _make_db(live, 'do-not-touch')
    backup = create_backup(
        database_path=live,
        media_root=tmp_path / 'media',
        env_file=None,
        backup_root=tmp_path / 'backups',
        retention=5,
        log_path=None,
    )
    refused = restore_backup(
        backup_dir=backup.path,
        target_dir=live.parent,
        live_database_path=live,
        replace_live=False,
        log_path=tmp_path / 'backup.log',
    )
    assert refused.verified is False
    assert 'Refusing' in refused.message
    assert _marker(live) == 'do-not-touch'
    assert not (live.parent / 'db.sqlite3.restore').exists()


def test_unverified_backup_is_not_restored(tmp_path):
    folder = tmp_path / 'FactoryOps-bad'
    folder.mkdir()
    result = restore_backup(backup_dir=folder, target_dir=tmp_path / 'out')
    assert result.verified is False
    assert not (tmp_path / 'out' / 'db.sqlite3').exists()


def test_backup_command_round_trip(tmp_path, settings):
    data = tmp_path / 'data'
    data.mkdir()
    database = data / 'db.sqlite3'
    _make_db(database, 'command')
    settings.DATABASES['default']['NAME'] = database
    env_file = tmp_path / 'factoryops.env'
    _env(env_file)
    log_path = tmp_path / 'backup.log'
    call_command(
        'backup_factoryops',
        database=str(database),
        media=str(tmp_path / 'media'),
        env_file=str(env_file),
        backup_root=str(tmp_path / 'backups'),
        retention=3,
        log=str(log_path),
    )
    backup_dir = next((tmp_path / 'backups').iterdir())
    scratch = tmp_path / 'scratch'
    call_command(
        'restore_factoryops',
        backup=str(backup_dir),
        target=str(scratch),
        log=str(log_path),
    )
    assert _marker(scratch / 'db.sqlite3') == 'command'
    assert _marker(database) == 'command'
    with pytest.raises(CommandError, match='Refusing'):
        call_command(
            'restore_factoryops',
            backup=str(backup_dir),
            target=str(data),
            log=str(log_path),
        )


def test_write_initial_env_from_process_environment(tmp_path, monkeypatch):
    from config.ops.envfile import write_initial_from_environment

    target = tmp_path / 'factoryops.env'
    secret = 's' * 64
    monkeypatch.setenv('FACTORYOPS_NEW_SECRET', secret)
    monkeypatch.setenv('FACTORYOPS_LAN', '10.1.1.5')
    monkeypatch.setenv('FACTORYOPS_HOSTNAME', 'FACTORY-PC')
    monkeypatch.setenv('FACTORYOPS_BIND', '0.0.0.0')
    monkeypatch.setenv('FACTORYOPS_PORT', '8000')
    monkeypatch.setenv('FACTORYOPS_SQLITE_PATH', r'C:\FactoryOps\data\db.sqlite3')
    monkeypatch.setenv('FACTORYOPS_MEDIA_ROOT', r'C:\FactoryOps\data\media')
    monkeypatch.setenv('FACTORYOPS_STATIC_ROOT', r'C:\FactoryOps\staticfiles')
    monkeypatch.setenv('FACTORYOPS_LOG_DIR', r'C:\FactoryOps\logs')
    monkeypatch.setenv('FACTORYOPS_BACKUP_DIR', r'C:\FactoryOps\backups')
    monkeypatch.setenv('FACTORYOPS_ENV_FILE', str(target))
    write_initial_from_environment()
    text = target.read_text(encoding='utf-8')
    assert f'SECRET_KEY={secret}' in text
    assert 'DEBUG=False' in text
    assert '10.1.1.5' in text
    assert 'change-this' not in text


def test_lan_update_preserves_secret_and_is_idempotent(tmp_path):
    secret = 's' * 64
    original = render_production_env(
        secret_key=secret,
        allowed_hosts=['localhost', '127.0.0.1'],
        csrf_origins=['http://127.0.0.1:8000'],
        bind='0.0.0.0',
        port=8000,
        sqlite_path=r'C:\FactoryOps\data\db.sqlite3',
        media_root=r'C:\FactoryOps\data\media',
        static_root=r'C:\FactoryOps\staticfiles',
        log_dir=r'C:\FactoryOps\logs',
        backup_dir=r'C:\FactoryOps\backups',
        retention=14,
        env_file=r'C:\FactoryOps\config\factoryops.env',
    )
    updated = apply_lan_address(
        original,
        lan='10.0.0.20',
        hostname='FACTORY-PC',
        port=8000,
    )
    assert f'SECRET_KEY={secret}' in updated
    assert '10.0.0.20' in updated
    assert 'FACTORY-PC' in updated
    assert 'localhost' in updated
    assert '*' not in updated.split('ALLOWED_HOSTS=', 1)[1].splitlines()[0]
    assert apply_lan_address(updated, lan='10.0.0.20', hostname='FACTORY-PC', port=8000) == updated
    path = tmp_path / 'factoryops.env'
    path.write_text(original, encoding='utf-8')
    call_command(
        'configure_lan',
        env_file=str(path),
        lan='10.0.0.20',
        hostname='FACTORY-PC',
        port=8000,
    )
    assert path.read_text(encoding='utf-8') == updated
