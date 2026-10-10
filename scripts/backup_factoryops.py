"""Database-safe backup of FactoryOps SQLite data and uploaded media.

Uses sqlite3.Connection.backup so a consistent snapshot can be taken while
the application is running. Each run writes a new timestamped directory and
does not replace the live database or an existing backup directory.
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


MANIFEST_NAME = 'manifest.json'
SNAPSHOT_NAME = 'db.sqlite3'
SQLITE_ENGINE = 'django.db.backends.sqlite3'


def _readonly_uri(path):
    return Path(path).resolve().as_uri() + '?mode=ro'


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _is_secret_name(name):
    return name == '.env' or name.startswith('.env')


def _outside(directory, parent):
    directory = Path(directory).resolve()
    parent = Path(parent).resolve()
    return directory != parent and parent not in directory.parents


def safe_relative(root, relative):
    """Resolve a manifest path and keep it inside root."""
    if not isinstance(relative, str) or not relative or relative.startswith(('/', '\\')):
        raise ValueError('Unsafe backup path.')
    if '\\' in relative or ':' in relative:
        raise ValueError('Unsafe backup path.')
    parts = Path(relative).parts
    if not parts or any(part in {'..', '.', ''} for part in parts):
        raise ValueError('Unsafe backup path.')
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError('Unsafe backup path.')
    return path


def assert_sqlite_engine(engine):
    if engine != SQLITE_ENGINE and 'sqlite3' not in str(engine):
        raise RuntimeError(
            'This backup only supports SQLite '
            f'({SQLITE_ENGINE}). Configured engine: {engine}.'
        )


def assert_destination_safe(destination, live_database):
    destination = Path(destination).resolve()
    if not live_database:
        raise ValueError('Refusing to restore without the live database path.')
    live = Path(live_database).resolve()
    if destination == live:
        raise ValueError('Refusing to overwrite the live database.')
    if (destination / SNAPSHOT_NAME).resolve() == live:
        raise ValueError('Refusing to overwrite the live database.')
    if destination == live.parent:
        raise ValueError('Refusing to restore into the live database directory.')


def default_backup_root():
    configured = os.environ.get('FACTORYOPS_BACKUP_DIR', '').strip()
    if configured:
        return Path(configured)
    return Path.home() / 'FactoryOpsBackups'


def setup_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    import django
    from django.conf import settings

    if not settings.configured:
        django.setup()


def configured_targets():
    """Read the database file and MEDIA_ROOT from the active Django settings."""
    from django.conf import settings

    database = settings.DATABASES['default']
    engine = database['ENGINE']
    name = database['NAME']
    if name in (None, '', ':memory:'):
        raise RuntimeError('The configured database is not a filesystem path.')
    media = settings.MEDIA_ROOT
    if not media:
        raise RuntimeError('MEDIA_ROOT is not configured.')
    return {
        'engine': engine,
        'database': Path(name),
        'media': Path(media),
        'application_root': Path(settings.BASE_DIR),
    }


def describe_media(status, media):
    media = Path(media)
    if status == 'absent':
        return f'MEDIA absent: {media} does not exist. No media files were copied.'
    if status == 'empty':
        return f'MEDIA empty: {media} contains no files. No media files were copied.'
    if status == 'copied':
        return f'MEDIA copied: files from {media} were stored with their relative paths.'
    raise ValueError(f'Unknown media status: {status}')


def describe_manifest_media(status):
    if status == 'absent':
        return 'MEDIA absent: this backup contains no media files.'
    if status == 'empty':
        return 'MEDIA empty: the backed-up media directory contains no files.'
    if status == 'copied':
        return 'MEDIA copied: backup media files matched the manifest.'
    raise ValueError(f'Unknown media status: {status}')


def integrity_check(path):
    uri = _readonly_uri(path)
    connection = None
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        row = connection.execute('PRAGMA integrity_check').fetchone()
    except sqlite3.DatabaseError as exc:
        raise RuntimeError('SQLite integrity check could not be completed.') from exc
    finally:
        if connection is not None:
            connection.close()
    if row is None or row[0] != 'ok':
        raise RuntimeError('SQLite integrity check failed.')
    return 'ok'


def backup_sqlite(source, destination):
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(f'Database file does not exist: {source}')
    if destination.resolve() == source.resolve():
        raise ValueError('Refusing to back up a database onto itself.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = None
    dest_conn = None
    try:
        source_conn = sqlite3.connect(_readonly_uri(source), uri=True, timeout=5.0)
        dest_conn = sqlite3.connect(destination, timeout=5.0)
        source_conn.backup(dest_conn)
        row = dest_conn.execute('PRAGMA integrity_check').fetchone()
    except sqlite3.DatabaseError as exc:
        if destination.exists() and destination.resolve() != source.resolve():
            destination.unlink(missing_ok=True)
        raise RuntimeError('SQLite backup could not be completed.') from exc
    finally:
        if dest_conn is not None:
            dest_conn.close()
        if source_conn is not None:
            source_conn.close()
    if row is None or row[0] != 'ok':
        destination.unlink(missing_ok=True)
        raise RuntimeError('Backup failed the SQLite integrity check.')


def copy_media(source, destination, forbid=None):
    source = Path(source)
    destination = Path(destination)
    if not source.exists():
        return 'absent'
    if not source.is_dir():
        raise NotADirectoryError(f'MEDIA_ROOT is not a directory: {source}')
    if destination.exists():
        raise FileExistsError(f'Media backup path already exists: {destination}')
    source_root = source.resolve()
    forbid_root = Path(forbid).resolve() if forbid else None
    copied = 0
    for path in source.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(_is_secret_name(part) for part in relative.parts):
            continue
        resolved = path.resolve()
        if resolved != source_root and source_root not in resolved.parents:
            continue
        if forbid_root is not None and (resolved == forbid_root or forbid_root in resolved.parents):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    if copied == 0:
        return 'empty'
    return 'copied'


def copy_listed_files(bundle, destination, manifest):
    copied = []
    for entry in manifest['files']:
        relative = entry['path']
        if relative == SNAPSHOT_NAME:
            continue
        source = safe_relative(bundle, relative)
        target = safe_relative(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative)
    return copied


def prune_backups(root, retention_days, now=None, keep=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    removed = []
    keep_path = Path(keep).resolve() if keep else None
    if not root.exists():
        return removed
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if keep_path is not None and child.resolve() == keep_path:
            continue
        modified = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            shutil.rmtree(child)
            removed.append(child)
    return removed


def _unique_bundle(destination_root, stamp):
    bundle = destination_root / stamp
    if not bundle.exists():
        return bundle
    for suffix in range(2, 1000):
        candidate = destination_root / f'{stamp}-{suffix}'
        if not candidate.exists():
            return candidate
    raise FileExistsError(f'Backup directory already exists: {bundle}')


def _bundle_files(bundle):
    files = []
    for path in sorted(bundle.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(bundle).as_posix()
        if relative == MANIFEST_NAME:
            continue
        if any(_is_secret_name(part) for part in Path(relative).parts):
            raise RuntimeError(f'Refusing to record a secret file in the backup: {relative}')
        files.append({
            'path': relative,
            'size': path.stat().st_size,
            'sha256': sha256_file(path),
        })
    return files


def write_manifest(bundle, created_at, database_engine, database_name, media_status):
    files = _bundle_files(bundle)
    if not any(item['path'] == SNAPSHOT_NAME for item in files):
        raise RuntimeError('Backup is missing the database snapshot.')
    manifest = {
        'created_at': created_at.isoformat(),
        'database_engine': database_engine,
        'database_name': database_name,
        'media_status': media_status,
        'media_copied': media_status == 'copied',
        'integrity_check': 'ok',
        'files': files,
    }
    target = bundle / MANIFEST_NAME
    target.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def validate_backup(bundle):
    bundle = Path(bundle).resolve()
    manifest_path = bundle / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f'Backup has no {MANIFEST_NAME}: {bundle}')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Backup manifest is not valid JSON: {bundle}') from exc
    if not isinstance(manifest, dict):
        raise ValueError('Backup manifest is not an object.')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('Backup manifest has no file list.')
    media_status = manifest.get('media_status')
    if media_status not in {'absent', 'empty', 'copied'}:
        raise ValueError('Backup manifest does not say whether media was included.')
    engine = manifest.get('database_engine')
    assert_sqlite_engine(engine)
    if manifest.get('integrity_check') != 'ok':
        raise RuntimeError('Backup manifest does not record a successful integrity check.')
    seen = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError('Backup manifest file entry is invalid.')
        relative = entry.get('path')
        expected_size = entry.get('size')
        expected_hash = entry.get('sha256')
        if (
            not isinstance(relative, str)
            or isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
        ):
            raise ValueError('Backup manifest file entry is incomplete.')
        path = safe_relative(bundle, relative)
        if not path.is_file():
            raise FileNotFoundError(f'Backup is missing {relative}.')
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise ValueError(f'Backup file size mismatch for {relative}.')
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash.lower():
            raise ValueError(f'Backup checksum mismatch for {relative}.')
        seen.add(relative)
    if SNAPSHOT_NAME not in seen:
        raise FileNotFoundError('Backup manifest does not include db.sqlite3.')
    media_files = [relative for relative in seen if relative.startswith('media/')]
    if media_status == 'copied' and not media_files:
        raise FileNotFoundError('Backup claims media was copied but no media files are listed.')
    if media_status in {'absent', 'empty'} and media_files:
        raise ValueError('Backup manifest lists media files but media was not recorded as copied.')
    for path in bundle.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(bundle).as_posix()
        if relative == MANIFEST_NAME:
            continue
        if relative not in seen:
            raise ValueError(f'Backup contains an unlisted file: {relative}.')
    integrity_check(bundle / SNAPSHOT_NAME)
    return manifest


def create_backup(
    database,
    media,
    destination_root,
    retention_days,
    application_root=None,
    now=None,
    database_engine=SQLITE_ENGINE,
):
    assert_sqlite_engine(database_engine)
    now = now or datetime.now(timezone.utc)
    database = Path(database).resolve()
    media = Path(media)
    destination_root = Path(destination_root).resolve()
    if not database.is_file():
        raise FileNotFoundError(f'Database file does not exist: {database}')
    guarded = [database.parent]
    if application_root:
        guarded.append(Path(application_root))
    for parent in guarded:
        if not _outside(destination_root, parent):
            raise ValueError(
                'Backup destination must be outside the application directory.'
            )
    if not _outside(destination_root, media):
        raise ValueError('Backup destination must not be inside the media directory.')
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    bundle = _unique_bundle(destination_root, stamp)
    try:
        bundle.mkdir(parents=True)
    except FileExistsError as exc:
        raise FileExistsError(
            f'Backup directory already exists and was not overwritten: {bundle}'
        ) from exc
    try:
        backup_sqlite(database, bundle / SNAPSHOT_NAME)
        media_status = copy_media(media, bundle / 'media', forbid=bundle)
        write_manifest(
            bundle,
            now,
            database_engine,
            database.name,
            media_status,
        )
        validate_backup(bundle)
        removed = prune_backups(destination_root, retention_days, now=now, keep=bundle)
    except Exception:
        shutil.rmtree(bundle, ignore_errors=True)
        raise
    return {
        'bundle': bundle,
        'removed': removed,
        'media_copied': media_status == 'copied',
        'media_status': media_status,
        'media_message': describe_media(media_status, media),
    }


def _retention_days(explicit):
    if explicit is not None:
        return explicit
    raw = os.environ.get('FACTORYOPS_BACKUP_RETENTION_DAYS', '').strip()
    if not raw:
        return 14
    return int(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Back up FactoryOps safely.')
    parser.add_argument('--database', default='')
    parser.add_argument('--media', default='')
    parser.add_argument('--destination', default='')
    parser.add_argument('--retention-days', type=int, default=None)
    parser.add_argument('--application-root', default='')
    parser.add_argument('--database-engine', default='')
    args = parser.parse_args(argv)
    if bool(args.database) != bool(args.media):
        print(
            'Pass both --database and --media, or omit both to use Django settings.',
            file=sys.stderr,
        )
        return 1
    try:
        retention = _retention_days(args.retention_days)
    except ValueError:
        print('retention-days must be an integer.', file=sys.stderr)
        return 1
    if retention < 1:
        print('retention-days must be at least 1.', file=sys.stderr)
        return 1
    if args.database:
        database = args.database
        media = args.media
        engine = args.database_engine or SQLITE_ENGINE
        application_root = args.application_root or None
    else:
        try:
            setup_django()
            targets = configured_targets()
        except Exception as exc:
            print(f'BACKUP FAILED: {exc}', file=sys.stderr)
            return 1
        database = targets['database']
        media = targets['media']
        engine = args.database_engine or targets['engine']
        application_root = args.application_root or targets['application_root']
    destination = args.destination or default_backup_root()
    try:
        result = create_backup(
            database,
            media,
            destination,
            retention,
            application_root=application_root,
            database_engine=engine,
        )
    except Exception as exc:
        print(f'BACKUP FAILED: {exc}', file=sys.stderr)
        return 1
    print(result['media_message'])
    print(f'BACKUP OK {result["bundle"]}')
    for path in result['removed']:
        print(f'PRUNED {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
