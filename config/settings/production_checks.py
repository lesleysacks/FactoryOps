"""Fail-closed checks for the factory PC production configuration.

These functions do not read Django's configured settings. Callers pass the
values they intend to use so tests can exercise them without booting the
production settings module.
"""

from django.core.exceptions import ImproperlyConfigured

PLACEHOLDER_SECRET_KEYS = {
    '',
    'change-this-to-a-long-random-secret-string',
    'changeme',
    'secret',
}
MINIMUM_SECRET_LENGTH = 50


def validate_production_config(
    *,
    secret_key,
    allowed_hosts,
    csrf_trusted_origins,
    debug,
    use_https,
):
    """Raise ImproperlyConfigured with a diagnostic list. Never echo the secret."""
    problems = []
    if debug:
        problems.append(
            'DEBUG is on. Production forces DEBUG off; do not bypass that.'
        )
    key = '' if secret_key is None else str(secret_key).strip()
    if key in PLACEHOLDER_SECRET_KEYS:
        problems.append(
            'SECRET_KEY is missing or still the example placeholder. '
            'Generate one with: python -c "from django.core.management.utils '
            'import get_random_secret_key; print(get_random_secret_key())"'
        )
    elif len(key) < MINIMUM_SECRET_LENGTH:
        problems.append(
            f'SECRET_KEY must be at least {MINIMUM_SECRET_LENGTH} characters.'
        )
    hosts = list(allowed_hosts or [])
    if not hosts:
        problems.append(
            'ALLOWED_HOSTS is empty. Set the factory PC name and its LAN address. '
            'Do not use a wildcard.'
        )
    if any(host.strip() == '*' for host in hosts):
        problems.append('ALLOWED_HOSTS must not contain *. The factory PC is not a public site.')
    origins = list(csrf_trusted_origins or [])
    if not origins:
        problems.append(
            'CSRF_TRUSTED_ORIGINS is empty. Set http://127.0.0.1:<port> and '
            'http://<lan-address>:<port> for each host operators and phones use.'
        )
    for origin in origins:
        if not (origin.startswith('http://') or origin.startswith('https://')):
            problems.append(
                f'CSRF trusted origin {origin!r} must start with http:// or https://.'
            )
        if use_https and not origin.startswith('https://'):
            problems.append(
                f'FACTORYOPS_USE_HTTPS is true, so {origin!r} must use https://.'
            )
    if problems:
        detail = '\n- '.join(problems)
        raise ImproperlyConfigured(
            'FactoryOps production configuration is incomplete:\n- ' + detail
        )
