"""Restore a FactoryOps backup into a separate directory.

This never replaces the live database. Promoting a restored copy onto the
factory PC is a manual step done while the server is stopped. The command
checks the manifest and checksums before it writes, and it refuses a
destination that resolves to the live database.
"""

import argparse
import shutil
import sys
from pathlib import Path

from scripts.backup_factoryops import (
    SNAPSHOT_NAME,
    assert_destination_safe,
    backup_sqlite,
    copy_listed_files,
    describe_manifest_media,
    validate_backup,
)


def restore_backup(bundle, destination, live_database=None):
    bundle = Path(bundle).resolve()
    destination = Path(destination).resolve()
    manifest = validate_backup(bundle)
    assert_destination_safe(destination, live_database)
    if destination == bundle or bundle in destination.parents or destination in bundle.parents:
        raise ValueError('Restore destination must be separate from the backup folder.')
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(
            f'Destination is not empty: {destination}. Choose a new folder.'
        )
    destination.mkdir(parents=True, exist_ok=True)
    try:
        target_db = destination / SNAPSHOT_NAME
        backup_sqlite(bundle / SNAPSHOT_NAME, target_db)
        copied = copy_listed_files(bundle, destination, manifest)
        if manifest['media_status'] == 'copied' and not copied:
            raise FileNotFoundError('Backup media files are missing. Restore was not completed.')
        for relative in copied:
            if not (destination / relative).is_file():
                raise FileNotFoundError(f'Restore is missing media file {relative}.')
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
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
        manifest_status = validate_backup(args.backup)['media_status']
    except Exception as exc:
        print(f'RESTORE FAILED: {exc}', file=sys.stderr)
        return 1
    print(describe_manifest_media(manifest_status))
    print(f'RESTORE OK {target}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
