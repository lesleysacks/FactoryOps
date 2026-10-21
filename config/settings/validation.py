"""Production configuration checks.

Imported by config.settings.production. Kept free of Django settings so tests
can call it without loading the production module.
"""

from django.core.exceptions import ImproperlyConfigured

PLACEHOLDER_SECRET = 'change-this-to-a-long-random-secret-string'
MIN_SECRET_LENGTH = 50


def parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in (raw or '').split(',') if item.strip()]


def validate_production_config(
    *,
    secret_key: str,
    debug: bool,
    allowed_hosts: list[str],
    csrf_trusted_origins: list[str],
    https: bool,
) -> None:
    """Raise ImproperlyConfigured when production settings are unsafe."""
    errors = []
    key = (secret_key or '').strip()
    if not key:
        errors.append(
            'SECRET_KEY is missing or empty. Generate one key and store it in '
            'the factory environment file. FactoryOps will not invent a new key '
            'on startup.'
        )
    elif key == PLACEHOLDER_SECRET or 'change-this' in key:
        errors.append(
            'SECRET_KEY is still the placeholder from .env.example. Generate a '
            'unique key and store it outside source control.'
        )
    elif len(key) < MIN_SECRET_LENGTH:
        errors.append(
            f'SECRET_KEY is too short ({len(key)} characters). Generate one with '
            'Django get_random_secret_key(); it must be at least '
            f'{MIN_SECRET_LENGTH} characters.'
        )

    if debug:
        errors.append(
            'DEBUG must be False for production settings. Refusing to start so '
            'factory users do not see tracebacks. Set DEBUG=False.'
        )

    if not allowed_hosts:
        errors.append(
            'ALLOWED_HOSTS is empty. Set the factory PC hostname, localhost, '
            '127.0.0.1, and the LAN address. Do not use a wildcard.'
        )
    elif any(host == '*' for host in allowed_hosts):
        errors.append('ALLOWED_HOSTS must not contain "*". List each host explicitly.')

    for origin in csrf_trusted_origins:
        if origin == '*' or '*' in origin:
            errors.append(f'CSRF_TRUSTED_ORIGINS entry {origin!r} must not use a wildcard.')
        elif not origin.startswith(('http://', 'https://')):
            errors.append(
                f'CSRF_TRUSTED_ORIGINS entry {origin!r} must start with http:// or https://.'
            )
        elif https and origin.startswith('http://'):
            errors.append(
                f'CSRF_TRUSTED_ORIGINS entry {origin!r} uses http:// while '
                'FACTORYOPS_HTTPS=True. Use https:// origins when HTTPS is enabled.'
            )

    if errors:
        joined = '\n- '.join(errors)
        raise ImproperlyConfigured(
            'FactoryOps production configuration is invalid and the server will '
            f'not start:\n- {joined}'
        )
