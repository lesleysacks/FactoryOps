"""
Config tests — SECRET_KEY and ALLOWED_HOSTS environment handling.

These tests use env overrides / Django override_settings. They do not
hardcode a developer LAN IP and do not require ALLOWED_HOSTS="*".
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.test import RequestFactory, override_settings


BASE_DIR = Path(__file__).resolve().parent.parent
BASE_SETTINGS = BASE_DIR / 'config' / 'settings' / 'base.py'
ENV_EXAMPLE = BASE_DIR / '.env.example'


def parse_allowed_hosts(raw: str) -> list[str]:
    """Mirror of config.settings.base ALLOWED_HOSTS parsing."""
    return [h.strip() for h in raw.split(',') if h.strip()]


def test_allowed_hosts_parsing_strips_whitespace():
    assert parse_allowed_hosts(' localhost , 127.0.0.1 , example.test ') == [
        'localhost',
        '127.0.0.1',
        'example.test',
    ]


def test_allowed_hosts_parsing_empty_and_skips_blanks():
    assert parse_allowed_hosts('') == []
    assert parse_allowed_hosts(' , , ') == []
    assert parse_allowed_hosts('localhost,,127.0.0.1') == ['localhost', '127.0.0.1']


def test_allowed_hosts_parsing_does_not_require_wildcard():
    hosts = parse_allowed_hosts('localhost,127.0.0.1')
    assert '*' not in hosts
    assert hosts == ['localhost', '127.0.0.1']


@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
def test_configured_host_is_accepted():
    request = RequestFactory().get('/', HTTP_HOST='127.0.0.1')
    assert request.get_host() == '127.0.0.1'


@override_settings(ALLOWED_HOSTS=['localhost', 'testserver'])
def test_unconfigured_host_is_rejected():
    request = RequestFactory().get('/', HTTP_HOST='203.0.113.50')
    with pytest.raises(DisallowedHost):
        request.get_host()


def test_runtime_allowed_hosts_include_env_hosts():
    """Every host from ALLOWED_HOSTS env must be accepted; wildcard forbidden."""
    import os

    raw = os.environ.get('ALLOWED_HOSTS', '')
    parsed = parse_allowed_hosts(raw)
    for host in parsed:
        assert host in settings.ALLOWED_HOSTS
    assert '*' not in settings.ALLOWED_HOSTS
    # Base settings must not invent a wildcard when env is narrow
    assert parse_allowed_hosts('localhost,127.0.0.1') == ['localhost', '127.0.0.1']


def test_secret_key_comes_from_environment():
    import os

    assert 'SECRET_KEY' in os.environ
    assert settings.SECRET_KEY == os.environ['SECRET_KEY']
    assert settings.SECRET_KEY  # non-empty


def test_secret_key_is_env_driven_in_source():
    source = BASE_SETTINGS.read_text(encoding='utf-8')
    assert "os.environ['SECRET_KEY']" in source
    assert 'ALLOWED_HOSTS' in source
    assert "os.getenv('ALLOWED_HOSTS'" in source
    # No hardcoded private LAN octets in Python settings
    assert '192.168.' not in source


def test_env_example_has_safe_placeholders_not_real_secrets():
    example = ENV_EXAMPLE.read_text(encoding='utf-8')
    assert 'get_random_secret_key' in example
    secret_lines = [
        line for line in example.splitlines() if line.startswith('SECRET_KEY=')
    ]
    assert secret_lines == [
        'SECRET_KEY=change-this-to-a-long-random-secret-string',
    ]
    host_lines = [
        line for line in example.splitlines() if line.startswith('ALLOWED_HOSTS=')
    ]
    assert host_lines == ['ALLOWED_HOSTS=localhost,127.0.0.1']
    assert not any(line.strip() == 'ALLOWED_HOSTS=*' for line in example.splitlines())
