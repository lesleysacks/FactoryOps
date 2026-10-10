"""SQLite backups use the backup API and restores stay off the live file."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from scripts.backup_factoryops import backup_sqlite, create_backup, main as backup_main, prune_backups
from scripts.restore_factoryops import main as restore_main, restore_backup


def _live_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute('create table pads (n integer)')
    connection.execute('insert into pads values (7)')
    connection.commit()
    connection.close()


def test_backup_round_trip_and_retention(tmp_path):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    media = app / 'media' / 'qc'
    media.mkdir(parents=True)
    (media / 'photo.jpg').write_bytes(b'jpeg')
    destination = tmp_path / 'backups'
    old = destination / 'old'
    old.mkdir(parents=True)
    aged = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
    os.utime(old, (aged, aged))

    result = create_backup(
        database,
        app / 'media',
        destination,
        14,
        application_root=app,
    )
    bundle = result['bundle']
    assert bundle.is_dir()
    assert not old.exists()
    assert (bundle / 'manifest.json').is_file()
    copied = sqlite3.connect(bundle / 'db.sqlite3')
    try:
        assert copied.execute('select n from pads').fetchone()[0] == 7
    finally:
        copied.close()
    assert (bundle / 'media' / 'qc' / 'photo.jpg').read_bytes() == b'jpeg'
    live = sqlite3.connect(database)
    try:
        assert live.execute('select n from pads').fetchone()[0] == 7
    finally:
        live.close()


def test_backup_refuses_a_destination_inside_the_application(tmp_path):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    with pytest.raises(ValueError, match='outside'):
        create_backup(database, app / 'media', app / 'backups', 14, application_root=app)


def test_backup_cli_reports_failure(tmp_path):
    app = tmp_path / 'app'
    destination = tmp_path / 'backups'
    code = backup_main(
        [
            '--database',
            str(app / 'missing.sqlite3'),
            '--media',
            str(app / 'media'),
            '--destination',
            str(destination),
            '--application-root',
            str(app),
        ]
    )
    assert code == 1
    assert list(destination.rglob('db.sqlite3')) == []


def test_restore_requires_confirmation_and_refuses_the_live_database(tmp_path, capsys):
    app = tmp_path / 'app'
    database = app / 'db.sqlite3'
    _live_database(database)
    bundle = create_backup(database, app / 'media', tmp_path / 'backups', 14, application_root=app)['bundle']

    separate = tmp_path / 'restored'
    code = restore_main(['--backup', str(bundle), '--destination', str(separate)])
    assert code == 1
    assert 'Nothing was written' in capsys.readouterr().err
    assert not separate.exists()

    with pytest.raises(ValueError, match='live database'):
        restore_backup(bundle, database.parent, live_database=database)
    live = sqlite3.connect(database)
    try:
        assert live.execute('select n from pads').fetchone()[0] == 7
    finally:
        live.close()

    code = restore_main(
        [
            '--backup',
            str(bundle),
            '--destination',
            str(separate),
            '--live-database',
            str(database),
            '--confirm',
        ]
    )
    assert code == 0
    restored = sqlite3.connect(separate / 'db.sqlite3')
    try:
        assert restored.execute('select n from pads').fetchone()[0] == 7
    finally:
        restored.close()
    assert database.is_file()


def test_prune_keeps_a_fresh_backup(tmp_path):
    fresh = tmp_path / 'fresh'
    fresh.mkdir()
    removed = prune_backups(tmp_path, 14)
    assert fresh not in removed
    assert fresh.exists()


def test_backup_sqlite_rejects_copying_onto_itself(tmp_path):
    database = tmp_path / 'db.sqlite3'
    _live_database(database)
    with pytest.raises(ValueError):
        backup_sqlite(database, database)
