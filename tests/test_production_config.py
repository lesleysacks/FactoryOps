"""Production settings fail closed and the WSGI entry point can boot."""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings.production_checks import validate_production_config


ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / 'scripts' / 'serve_production.py'
LONG_SECRET = 'p' * 64


def test_placeholder_secret_is_rejected():
    with pytest.raises(ImproperlyConfigured) as caught:
        validate_production_config(
            secret_key='change-this-to-a-long-random-secret-string',
            allowed_hosts=['localhost'],
            csrf_trusted_origins=['http://127.0.0.1:8000'],
            debug=False,
            use_https=False,
        )
    message = str(caught.value)
    assert 'placeholder' in message
    assert 'change-this-to-a-long-random-secret-string' not in message


def test_short_secret_empty_hosts_wildcard_and_https_mismatch_are_rejected():
    with pytest.raises(ImproperlyConfigured) as caught:
        validate_production_config(
            secret_key='short',
            allowed_hosts=[],
            csrf_trusted_origins=[],
            debug=True,
            use_https=False,
        )
    message = str(caught.value)
    assert 'at least 50' in message
    assert 'ALLOWED_HOSTS is empty' in message
    assert 'CSRF_TRUSTED_ORIGINS is empty' in message
    assert 'DEBUG is on' in message

    with pytest.raises(ImproperlyConfigured) as wildcard:
        validate_production_config(
            secret_key=LONG_SECRET,
            allowed_hosts=['*'],
            csrf_trusted_origins=['http://127.0.0.1:8000'],
            debug=False,
            use_https=False,
        )
    assert 'must not contain *' in str(wildcard.value)

    with pytest.raises(ImproperlyConfigured) as https:
        validate_production_config(
            secret_key=LONG_SECRET,
            allowed_hosts=['localhost'],
            csrf_trusted_origins=['http://127.0.0.1:8000'],
            debug=False,
            use_https=True,
        )
    assert 'https://' in str(https.value)


def test_valid_config_is_accepted():
    validate_production_config(
        secret_key=LONG_SECRET,
        allowed_hosts=['localhost', '127.0.0.1'],
        csrf_trusted_origins=['http://127.0.0.1:8000', 'http://localhost:8000'],
        debug=False,
        use_https=False,
    )


def test_python_settings_do_not_hardcode_a_lan_address():
    for relative in ('config/settings/base.py', 'config/settings/production.py'):
        source = (ROOT / relative).read_text(encoding='utf-8')
        assert '192.168.' not in source
        assert 'ALLOWED_HOSTS' not in source or '*' not in source.split('ALLOWED_HOSTS', 1)[-1][:80]


def _production_env(tmp_path, **overrides):
    env = os.environ.copy()
    env.update(
        {
            'DJANGO_SETTINGS_MODULE': 'config.settings.production',
            'SECRET_KEY': LONG_SECRET,
            'ALLOWED_HOSTS': 'localhost,127.0.0.1',
            'CSRF_TRUSTED_ORIGINS': 'http://127.0.0.1:8000,http://localhost:8000',
            'DEBUG': 'True',
            'FACTORYOPS_USE_HTTPS': 'False',
            'FACTORYOPS_LOG_DIR': str(tmp_path / 'logs'),
            'FACTORYOPS_DB_PATH': str(tmp_path / 'db.sqlite3'),
            'FACTORYOPS_MEDIA_ROOT': str(tmp_path / 'media'),
        }
    )
    env.update(overrides)
    return env


def test_serve_check_fails_on_placeholder_secret(tmp_path):
    env = _production_env(
        tmp_path,
        SECRET_KEY='change-this-to-a-long-random-secret-string',
    )
    completed = subprocess.run(
        [sys.executable, str(SERVE), '--check'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert 'placeholder' in completed.stderr
    assert LONG_SECRET not in completed.stderr
    assert 'change-this-to-a-long-random-secret-string' not in completed.stderr


def test_serve_check_succeeds_and_forces_debug_off(tmp_path):
    env = _production_env(tmp_path)
    completed = subprocess.run(
        [sys.executable, str(SERVE), '--check'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert 'production configuration ok' in completed.stdout
    assert 'DEBUG is on' not in completed.stderr


def test_production_example_keeps_the_placeholder_secret():
    example = (ROOT / '.env.production.example').read_text(encoding='utf-8')
    secret_lines = [
        line for line in example.splitlines() if line.startswith('SECRET_KEY=')
    ]
    assert secret_lines == ['SECRET_KEY=change-this-to-a-long-random-secret-string']
    assert 'ALLOWED_HOSTS=*' not in example
    assert 'DEBUG=False' in example


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_waitress_serves_health_and_rejects_unknown_hosts(tmp_path):
    port = _free_port()
    env = _production_env(
        tmp_path,
        FACTORYOPS_BIND='127.0.0.1',
        FACTORYOPS_PORT=str(port),
        CSRF_TRUSTED_ORIGINS=f'http://127.0.0.1:{port}',
    )
    (tmp_path / 'media').mkdir()
    migrated = subprocess.run(
        [sys.executable, str(ROOT / 'manage.py'), 'migrate', '--noinput'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert migrated.returncode == 0, migrated.stderr
    process = subprocess.Popen(
        [sys.executable, str(SERVE)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    health_url = f'http://127.0.0.1:{port}/health/'
    try:
        body = ''
        deadline = time.time() + 20
        while time.time() < deadline:
            if process.poll() is not None:
                output = process.stdout.read()
                raise AssertionError(f'server exited early: {output}')
            try:
                with urllib.request.urlopen(health_url, timeout=1) as response:
                    body = response.read().decode('utf-8')
                    assert response.status == 200
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.2)
        else:
            raise AssertionError('health check did not respond')

        assert body == '{"status": "ok"}'
        assert LONG_SECRET not in body

        login_url = f'http://127.0.0.1:{port}/accounts/login/'
        with urllib.request.urlopen(login_url, timeout=5) as response:
            login = response.read().decode('utf-8')
            assert response.status == 200
        assert 'password' in login.lower()
        assert LONG_SECRET not in login

        request = urllib.request.Request(health_url, headers={'Host': 'evil.example'})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        assert caught.value.code == 400
        error_body = caught.value.read().decode('utf-8', errors='replace')
        assert LONG_SECRET not in error_body
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
