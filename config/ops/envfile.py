"""Production environment-file helpers.

The Windows installer calls these functions. They never print SECRET_KEY and
they refuse to replace an existing file's key during a LAN-address update.
"""

from __future__ import annotations

from config.settings.validation import PLACEHOLDER_SECRET, MIN_SECRET_LENGTH


class EnvFileError(ValueError):
    pass


def _reject_host(host: str) -> str:
    cleaned = host.strip()
    if not cleaned or any(char.isspace() for char in cleaned):
        raise EnvFileError(f'Invalid host {host!r}.')
    if cleaned == '*' or '*' in cleaned or '/' in cleaned:
        raise EnvFileError(f'Host {cleaned!r} is not allowed. Do not use a wildcard.')
    return cleaned


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def build_allowed_hosts(extra: list[str], hostname: str = '') -> list[str]:
    hosts = ['localhost', '127.0.0.1']
    if hostname.strip():
        hosts.append(_reject_host(hostname))
    for item in extra:
        if item.strip():
            hosts.append(_reject_host(item))
    return dedupe(hosts)


def build_csrf_origins(hosts: list[str], port: int, https: bool = False) -> list[str]:
    if port < 1 or port > 65535:
        raise EnvFileError(f'Port {port} is outside 1-65535.')
    scheme = 'https' if https else 'http'
    return [f'{scheme}://{host}:{port}' for host in hosts]


def upsert_env(text: str, updates: dict[str, str]) -> str:
    """Replace named keys and append any that are missing. Other lines stay."""
    seen = set()
    output = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            output.append(line)
            continue
        key, _value = line.split('=', 1)
        name = key.strip()
        if name in updates:
            output.append(f'{name}={updates[name]}')
            seen.add(name)
        else:
            output.append(line)
    for name, value in updates.items():
        if name not in seen:
            output.append(f'{name}={value}')
    rendered = '\n'.join(output)
    if text.endswith('\n') or rendered:
        rendered += '\n'
    return rendered


def render_production_env(
    *,
    secret_key: str,
    allowed_hosts: list[str],
    csrf_origins: list[str],
    bind: str,
    port: int,
    sqlite_path: str,
    media_root: str,
    static_root: str,
    log_dir: str,
    backup_dir: str,
    retention: int,
    env_file: str,
    https: bool = False,
) -> str:
    key = secret_key.strip()
    if key == PLACEHOLDER_SECRET or 'change-this' in key or len(key) < MIN_SECRET_LENGTH:
        raise EnvFileError(
            'Refusing to write a placeholder or short SECRET_KEY. Generate a key '
            'once and keep it in the factory environment file.'
        )
    if not allowed_hosts or any(host == '*' for host in allowed_hosts):
        raise EnvFileError('ALLOWED_HOSTS must list explicit hosts and must not contain "*".')
    lines = [
        '# FactoryOps production environment. Do not commit this file.',
        '# Generated once by the installer. Later installs do not rotate SECRET_KEY.',
        f'SECRET_KEY={key}',
        'DEBUG=False',
        'DJANGO_SETTINGS_MODULE=config.settings.production',
        'ALLOWED_HOSTS=' + ','.join(allowed_hosts),
        'CSRF_TRUSTED_ORIGINS=' + ','.join(csrf_origins),
        f'FACTORYOPS_BIND={bind}',
        f'FACTORYOPS_PORT={port}',
        f'FACTORYOPS_HTTPS={"True" if https else "False"}',
        f'FACTORYOPS_SQLITE_PATH={sqlite_path}',
        f'FACTORYOPS_MEDIA_ROOT={media_root}',
        f'FACTORYOPS_STATIC_ROOT={static_root}',
        f'FACTORYOPS_LOG_DIR={log_dir}',
        f'FACTORYOPS_BACKUP_DIR={backup_dir}',
        f'FACTORYOPS_BACKUP_RETENTION={retention}',
        f'FACTORYOPS_ENV_FILE={env_file}',
    ]
    return '\n'.join(lines) + '\n'


def write_initial_from_environment() -> None:
    """Write the production env file from process environment variables.

    The Windows installer sets these variables and does not pass SECRET_KEY
    on the command line. FACTORYOPS_NEW_SECRET is required and is not logged.
    """
    import os
    from pathlib import Path

    secret = os.environ.get('FACTORYOPS_NEW_SECRET', '')
    port = int(os.environ['FACTORYOPS_PORT'])
    https = os.environ.get('FACTORYOPS_HTTPS', 'False') == 'True'
    hosts = build_allowed_hosts(
        [os.environ.get('FACTORYOPS_LAN', '')],
        hostname=os.environ.get('FACTORYOPS_HOSTNAME', ''),
    )
    text = render_production_env(
        secret_key=secret,
        allowed_hosts=hosts,
        csrf_origins=build_csrf_origins(hosts, port, https),
        bind=os.environ.get('FACTORYOPS_BIND', '0.0.0.0'),
        port=port,
        sqlite_path=os.environ['FACTORYOPS_SQLITE_PATH'],
        media_root=os.environ['FACTORYOPS_MEDIA_ROOT'],
        static_root=os.environ['FACTORYOPS_STATIC_ROOT'],
        log_dir=os.environ['FACTORYOPS_LOG_DIR'],
        backup_dir=os.environ['FACTORYOPS_BACKUP_DIR'],
        retention=int(os.environ.get('FACTORYOPS_BACKUP_RETENTION', '14')),
        env_file=os.environ['FACTORYOPS_ENV_FILE'],
        https=https,
    )
    Path(os.environ['FACTORYOPS_ENV_FILE']).write_text(text, encoding='utf-8')


def apply_lan_address(text: str, *, lan: str, hostname: str, port: int, https: bool = False) -> str:
    """Update host and CSRF lines. Leave SECRET_KEY and every other line alone."""
    hosts = build_allowed_hosts([lan], hostname=hostname)
    origins = build_csrf_origins(hosts, port, https=https)
    return upsert_env(
        text,
        {
            'ALLOWED_HOSTS': ','.join(hosts),
            'CSRF_TRUSTED_ORIGINS': ','.join(origins),
            'FACTORYOPS_PORT': str(port),
            'FACTORYOPS_HTTPS': 'True' if https else 'False',
        },
    )
