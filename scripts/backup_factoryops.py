"""Database-safe backup of FactoryOps SQLite data and uploaded media.

Uses sqlite3.Connection.backup so the live database is not copied as a raw
file while writes may be in progress. The backup is a new timestamped
directory. This script never deletes or replaces the live database.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _readonly_uri(path):
    return Path(path).resolve().as_uri() + '?mode=ro'


def backup_sqlite(source, destination):
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f'Database file does not exist: {source}')
    if destination.resolve() == source.resolve():
        raise ValueError('Refusing to back up a database onto itself.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(_readonly_uri(source), uri=True)
    dest_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(dest_conn)
        row = dest_conn.execute('PRAGMA integrity_check').fetchone()
    finally:
        dest_conn.close()
        source_conn.close()
    if row is None or row[0] != 'ok':
        destination.unlink(missing_ok=True)
        raise RuntimeError('Backup failed the SQLite integrity check.')


def copy_media(source, destination):
    source = Path(source)
    destination = Path(destination)
    if not source.exists():
        return False
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return True


def prune_backups(root, retention_days, now=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    removed = []
    if not root.exists():
        return removed
    for child in root.iterdir():
        if not child.is_dir():
            continue
        modified = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            shutil.rmtree(child)
            removed.append(child)
    return removed


def _outside(directory, parent):
    directory = Path(directory).resolve()
    parent = Path(parent).resolve()
    return directory != parent and parent not in directory.parents


def create_backup(
    database,
    media,
    destination_root,
    retention_days,
    application_root=None,
    now=None,
):
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    bundle = Path(destination_root) / stamp
    if bundle.exists():
        raise FileExistsError(f'Backup directory already exists: {bundle}')
    database = Path(database).resolve()
    destination_root = Path(destination_root).resolve()
    guarded = [database.parent]
    if application_root:
        guarded.append(Path(application_root))
    for parent in guarded:
        if not _outside(destination_root, parent):
            raise ValueError(
                'Backup destination must be outside the application directory.'
            )
    bundle.mkdir(parents=True)
    db_copy = bundle / 'db.sqlite3'
    try:
        backup_sqlite(database, db_copy)
        media_copied = copy_media(media, bundle / 'media')
        manifest = {
            'created_at': now.isoformat(),
            'database_name': database.name,
            'media_copied': media_copied,
        }
        (bundle / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        removed = prune_backups(destination_root, retention_days, now=now)
    except Exception:
        shutil.rmtree(bundle, ignore_errors=True)
        raise
    return {'bundle': bundle, 'removed': removed, 'media_copied': media_copied}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Back up FactoryOps safely.')
    parser.add_argument('--database', required=True)
    parser.add_argument('--media', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--retention-days', type=int, default=14)
    parser.add_argument('--application-root', default='')
    args = parser.parse_args(argv)
    if args.retention_days < 1:
        print('retention-days must be at least 1.', file=sys.stderr)
        return 1
    try:
        result = create_backup(
            args.database,
            args.media,
            args.destination,
            args.retention_days,
            application_root=args.application_root or None,
        )
    except Exception as exc:
        print(f'BACKUP FAILED: {exc}', file=sys.stderr)
        return 1
    print(f'BACKUP OK {result["bundle"]}')
    for path in result['removed']:
        print(f'PRUNED {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
