"""SQLite and media backup.

The database copy uses sqlite3.Connection.backup. A plain file copy of SQLite
while Waitress is writing is not used. This module does not import Django.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BACKUP_PREFIX = 'FactoryOps-'
REDACT_MARKERS = ('SECRET', 'PASSWORD', 'TOKEN', 'KEY')


@dataclass
class BackupResult:
    path: Path | None
    verified: bool
    message: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def append_log(log_path: Path | None, level: str, message: str) -> None:
    line = f'{_now().isoformat()} {level} factoryops.backup {message}'
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')


def redact_env_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            lines.append(line)
            continue
        key, _value = line.split('=', 1)
        if any(marker in key.upper() for marker in REDACT_MARKERS):
            lines.append(f'{key.strip()}=REDACTED')
        else:
            lines.append(line)
    rendered = '\n'.join(lines)
    if text.endswith('\n') or rendered:
        rendered += '\n'
    return rendered


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def integrity_check(database_path: Path) -> str:
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute('PRAGMA integrity_check').fetchone()
    finally:
        connection.close()
    return row[0] if row else 'missing'


def copy_database(source: Path, destination: Path) -> None:
    """Consistent snapshot. Opens the source read-only so the backup cannot write it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = source.resolve().as_uri() + '?mode=ro'
    source_conn = sqlite3.connect(source_uri, uri=True)
    dest_conn = sqlite3.connect(destination)
    try:
        with dest_conn:
            source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()


def _media_files(media_root: Path) -> list[Path]:
    if not media_root.exists():
        return []
    return sorted(path for path in media_root.rglob('*') if path.is_file())


def verify_backup(backup_dir: Path) -> tuple[bool, str]:
    manifest_path = backup_dir / 'manifest.json'
    if not manifest_path.is_file():
        return False, 'manifest.json is missing'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return False, 'manifest.json is not valid JSON'
    database = backup_dir / manifest.get('database', {}).get('file', '')
    if not database.is_file():
        return False, 'database file is missing from the backup'
    expected_hash = manifest.get('database', {}).get('sha256')
    if sha256_file(database) != expected_hash:
        return False, 'database hash does not match the manifest'
    integrity = integrity_check(database)
    if integrity != 'ok':
        return False, f'database integrity check failed: {integrity}'
    for entry in manifest.get('media', []):
        media_path = backup_dir / entry['path']
        if not media_path.is_file():
            return False, f'missing media file {entry["path"]}'
        if sha256_file(media_path) != entry['sha256']:
            return False, f'media hash mismatch for {entry["path"]}'
    config_name = manifest.get('config')
    if config_name:
        env_path = backup_dir / config_name
        if not env_path.is_file():
            return False, 'redacted configuration file is missing'
        redacted = env_path.read_text(encoding='utf-8')
        for line in redacted.splitlines():
            if line.startswith('SECRET_KEY=') and line != 'SECRET_KEY=REDACTED':
                return False, 'redacted configuration still contains a SECRET_KEY value'
    return True, 'ok'


def _verified_backups(backup_root: Path) -> list[Path]:
    found = []
    if not backup_root.exists():
        return found
    for path in backup_root.iterdir():
        if not path.is_dir() or not path.name.startswith(BACKUP_PREFIX):
            continue
        manifest_path = path / 'manifest.json'
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if manifest.get('verified') is True:
            found.append(path)
    return sorted(found, key=lambda item: item.name)


def prune_verified_backups(backup_root: Path, retention: int, keep: Path) -> list[Path]:
    """Delete older verified backups only. Unverified directories are left in place."""
    retention = max(int(retention), 1)
    verified = _verified_backups(backup_root)
    survivors = set(verified[-retention:])
    survivors.add(keep)
    removed = []
    for path in verified:
        if path in survivors or path == keep:
            continue
        shutil.rmtree(path)
        removed.append(path)
    return removed


def create_backup(
    *,
    database_path: Path,
    media_root: Path,
    env_file: Path | None,
    backup_root: Path,
    retention: int,
    log_path: Path | None = None,
) -> BackupResult:
    database_path = Path(database_path)
    media_root = Path(media_root)
    backup_root = Path(backup_root)
    if not database_path.is_file():
        message = f'Database file does not exist: {database_path}'
        append_log(log_path, 'ERROR', message)
        return BackupResult(None, False, message)

    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = _now().strftime('%Y%m%dT%H%M%S%fZ')
    destination = backup_root / f'{BACKUP_PREFIX}{stamp}'
    suffix = 0
    while destination.exists():
        suffix += 1
        destination = backup_root / f'{BACKUP_PREFIX}{stamp}-{suffix}'
    destination.mkdir()
    try:
        database_copy = destination / 'db.sqlite3'
        copy_database(database_path, database_copy)
        media_entries = []
        for source in _media_files(media_root):
            relative = Path('media') / source.relative_to(media_root)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            media_entries.append({
                'path': relative.as_posix(),
                'sha256': sha256_file(target),
            })
        config_name = None
        if env_file is not None and Path(env_file).is_file():
            config_name = 'factoryops.env.redacted'
            redacted = redact_env_text(Path(env_file).read_text(encoding='utf-8'))
            (destination / config_name).write_text(redacted, encoding='utf-8')
        manifest = {
            'created_at': _now().isoformat(),
            'verified': False,
            'database': {
                'file': 'db.sqlite3',
                'sha256': sha256_file(database_copy),
                'integrity': integrity_check(database_copy),
            },
            'media': media_entries,
            'config': config_name,
            'note': (
                'Secrets are not included. Keep the real environment file with '
                'the factory PC or in a password manager.'
            ),
        }
        (destination / 'manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n',
            encoding='utf-8',
        )
        ok, detail = verify_backup(destination)
        if not ok:
            raise RuntimeError(detail)
        manifest['verified'] = True
        (destination / 'manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n',
            encoding='utf-8',
        )
        ok, detail = verify_backup(destination)
        if not ok:
            raise RuntimeError(detail)
        removed = prune_verified_backups(backup_root, retention, destination)
        message = (
            f'Backup verified at {destination}. '
            f'Removed {len(removed)} older verified backup(s).'
        )
        append_log(log_path, 'INFO', message)
        return BackupResult(destination, True, message)
    except Exception as exc:
        message = f'Backup failed and was not verified: {exc}'
        append_log(log_path, 'ERROR', message)
        shutil.rmtree(destination, ignore_errors=True)
        return BackupResult(None, False, message)


def _same_path(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def restore_backup(
    *,
    backup_dir: Path,
    target_dir: Path,
    live_database_path: Path | None = None,
    live_media_root: Path | None = None,
    replace_live: bool = False,
    log_path: Path | None = None,
) -> BackupResult:
    """Restore into target_dir. Refuses to replace the live files unless asked."""
    backup_dir = Path(backup_dir)
    target_dir = Path(target_dir)
    ok, detail = verify_backup(backup_dir)
    if not ok:
        message = f'Refusing to restore an unverified backup: {detail}'
        append_log(log_path, 'ERROR', message)
        return BackupResult(None, False, message)
    manifest = json.loads((backup_dir / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('verified') is not True:
        message = 'Refusing to restore a backup that is not marked verified.'
        append_log(log_path, 'ERROR', message)
        return BackupResult(None, False, message)

    target_dir.mkdir(parents=True, exist_ok=True)
    target_database = target_dir / 'db.sqlite3'
    target_media = target_dir / 'media'
    if not replace_live:
        if live_database_path is not None and _same_path(target_database, Path(live_database_path)):
            message = (
                'Refusing to overwrite the live database. Pass a different '
                '--target to test the restore, or pass --replace-live only '
                'after the server is stopped and you intend to replace production data.'
            )
            append_log(log_path, 'ERROR', message)
            return BackupResult(None, False, message)
        if live_media_root is not None and Path(live_media_root).exists() and _same_path(
            target_media, Path(live_media_root)
        ):
            message = 'Refusing to overwrite the live media directory.'
            append_log(log_path, 'ERROR', message)
            return BackupResult(None, False, message)

    temporary = target_dir / 'db.sqlite3.restore'
    try:
        copy_database(backup_dir / 'db.sqlite3', temporary)
        if integrity_check(temporary) != 'ok':
            raise RuntimeError('restored database failed integrity check')
        temporary.replace(target_database)
        for suffix in ('-wal', '-shm'):
            sidecar = Path(str(target_database) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        media_source = backup_dir / 'media'
        if media_source.exists():
            shutil.copytree(media_source, target_media, dirs_exist_ok=True)
        message = f'Restore verified in {target_dir}.'
        append_log(log_path, 'INFO', message)
        return BackupResult(target_dir, True, message)
    except Exception as exc:
        message = f'Restore failed: {exc}'
        append_log(log_path, 'ERROR', message)
        if temporary.exists():
            temporary.unlink()
        return BackupResult(None, False, message)
