"""Restore a FactoryOps backup into a separate directory.

This never replaces the live database. Promoting a restored copy onto the
factory PC is a manual step done while the server is stopped.
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path


def restore_backup(bundle, destination, live_database=None):
    bundle = Path(bundle).resolve()
    destination = Path(destination).resolve()
    database = bundle / 'db.sqlite3'
    if not database.is_file():
        raise FileNotFoundError(f'Backup has no db.sqlite3: {bundle}')
    if live_database is not None and destination == Path(live_database).resolve().parent:
        raise ValueError('Refusing to restore into the live database directory.')
    if live_database is not None and (destination / 'db.sqlite3').resolve() == Path(live_database).resolve():
        raise ValueError('Refusing to overwrite the live database.')
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(
            f'Destination is not empty: {destination}. Choose a new folder.'
        )
    destination.mkdir(parents=True, exist_ok=True)
    target_db = destination / 'db.sqlite3'
    source = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)
    copied = sqlite3.connect(target_db)
    try:
        source.backup(copied)
        row = copied.execute('PRAGMA integrity_check').fetchone()
    finally:
        copied.close()
        source.close()
    if row is None or row[0] != 'ok':
        raise RuntimeError('Restored database failed the SQLite integrity check.')
    media = bundle / 'media'
    if media.exists():
        shutil.copytree(media, destination / 'media')
    return target_db


def main(argv=None):
    parser = argparse.ArgumentParser(description='Restore FactoryOps to a separate folder.')
    parser.add_argument('--backup', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--live-database', default='')
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args(argv)
    if not args.confirm:
        print('Re-run with --confirm. Nothing was written.', file=sys.stderr)
        return 1
    try:
        target = restore_backup(
            args.backup,
            args.destination,
            live_database=args.live_database or None,
        )
    except Exception as exc:
        print(f'RESTORE FAILED: {exc}', file=sys.stderr)
        return 1
    print(f'RESTORE OK {target}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
