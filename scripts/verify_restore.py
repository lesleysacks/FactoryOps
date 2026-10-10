"""Verify a FactoryOps backup against a disposable database copy.

This checks the manifest, file checksums, and SQLite integrity, then runs
migrations and Django checks on a copy. It never opens the live database
for writing and it never replaces the live database.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.backup_factoryops import (
    SNAPSHOT_NAME,
    assert_destination_safe,
    backup_sqlite,
    configured_targets,
    copy_listed_files,
    describe_manifest_media,
    setup_django,
    validate_backup,
)


def _same_path(left, right):
    return Path(left).resolve() == Path(right).resolve()


def exercise_child():
    """Migrate a disposable copy in a separate process.

    The database path is taken from the environment and compared with the
    live file before Django applications start.
    """
    target = Path(os.environ['FACTORYOPS_RESTORE_VERIFY_DATABASE']).resolve()
    live = Path(os.environ['FACTORYOPS_RESTORE_VERIFY_LIVE']).resolve()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    from django.conf import settings

    configured = Path(settings.DATABASES['default']['NAME']).resolve()
    if target == live or target == configured:
        raise SystemExit('Refusing to run migrations against the live database.')
    settings.DATABASES['default']['NAME'] = str(target)
    settings.DATABASES['default']['ENGINE'] = 'django.db.backends.sqlite3'
    import django
    django.setup()
    from django.core import checks
    from django.core.management import call_command
    from django.db import connections

    connections.close_all()
    active = Path(settings.DATABASES['default']['NAME']).resolve()
    if active != target or active == live or active == configured:
        raise SystemExit('Refusing to run migrations against the live database.')
    call_command('migrate', interactive=False, verbosity=0)
    issues = checks.run_checks(databases=['default'])
    serious = [issue for issue in issues if issue.level >= checks.ERROR]
    if serious:
        summary = '; '.join(f'{issue.id}: {issue.msg}' for issue in serious)
        raise SystemExit(f'Django checks failed for the disposable database: {summary}')


def exercise_disposable_database(database_path, live_database):
    """Apply migrations and Django checks to a copy, never to the live file."""
    database_path = Path(database_path).resolve()
    live_database = Path(live_database).resolve()
    if _same_path(database_path, live_database):
        raise ValueError('Refusing to run migrations against the live database.')
    env = os.environ.copy()
    env['FACTORYOPS_RESTORE_VERIFY_DATABASE'] = str(database_path)
    env['FACTORYOPS_RESTORE_VERIFY_LIVE'] = str(live_database)
    env.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    completed = subprocess.run(
        [sys.executable, '-c', 'from scripts.verify_restore import exercise_child; exercise_child()'],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or 'disposable database checks failed').strip()
        if 'SECRET_KEY=' in detail or 'PASSWORD=' in detail:
            detail = 'disposable database checks failed'
        tail = '\n'.join(detail.splitlines()[-8:])
        raise RuntimeError(tail or 'disposable database checks failed')


def _write_rehearsal(bundle, destination, manifest):
    target = destination / SNAPSHOT_NAME
    backup_sqlite(bundle / SNAPSHOT_NAME, target)
    copied = copy_listed_files(bundle, destination, manifest)
    if manifest['media_status'] == 'copied' and not copied:
        raise FileNotFoundError('Backup media files were not written to the rehearsal directory.')
    for relative in copied:
        if not (destination / relative).is_file():
            raise FileNotFoundError(f'Rehearsal is missing media file {relative}.')
    return target


def verify_restore(bundle, destination=None, live_database=None, exercise_django=True):
    bundle = Path(bundle).resolve()
    manifest = validate_backup(bundle)
    if live_database is None:
        live_database = configured_targets()['database']
    live_database = Path(live_database).resolve()
    owns_temp = destination is None
    if owns_temp:
        destination = Path(tempfile.mkdtemp(prefix='factoryops-restore-'))
        existed = True
        try:
            assert_destination_safe(destination, live_database)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    else:
        destination = Path(destination).resolve()
        assert_destination_safe(destination, live_database)
        if destination == bundle or bundle in destination.parents or destination in bundle.parents:
            raise ValueError('Restore destination must be separate from the backup folder.')
        if destination.exists() and any(destination.iterdir()):
            raise FileExistsError(
                f'Destination is not empty: {destination}. Choose a new folder.'
            )
        existed = destination.exists()
    try:
        destination.mkdir(parents=True, exist_ok=True)
        target = _write_rehearsal(bundle, destination, manifest)
        if exercise_django:
            exercise_disposable_database(target, live_database)
    except Exception:
        if owns_temp or not existed:
            shutil.rmtree(destination, ignore_errors=True)
        else:
            (destination / SNAPSHOT_NAME).unlink(missing_ok=True)
            shutil.rmtree(destination / 'media', ignore_errors=True)
        raise
    messages = [
        describe_manifest_media(manifest['media_status']),
        'Manifest checksums verified.',
        'SQLite integrity check passed.',
    ]
    if exercise_django:
        messages.append('Migrations and Django checks passed on the disposable copy.')
    messages.append(f'Live database was not modified: {live_database}')
    if owns_temp:
        messages.append(f'Disposable copy removed: {destination}')
        shutil.rmtree(destination, ignore_errors=True)
    return {
        'destination': destination,
        'kept': not owns_temp,
        'database': destination / SNAPSHOT_NAME,
        'media_status': manifest['media_status'],
        'messages': messages,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Verify a FactoryOps backup on a disposable copy. The live database is not modified.'
    )
    parser.add_argument('--backup', required=True)
    parser.add_argument('--destination', default='')
    parser.add_argument('--live-database', default='')
    args = parser.parse_args(argv)
    try:
        if not args.live_database:
            setup_django()
        outcome = verify_restore(
            args.backup,
            destination=args.destination or None,
            live_database=args.live_database or None,
        )
    except Exception as exc:
        print(f'VERIFY FAILED: {exc}', file=sys.stderr)
        return 1
    for line in outcome['messages']:
        print(line)
    print(f'VERIFY OK {outcome["destination"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
