"""Production settings, health endpoint, and offline-asset checks."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import User
from config.settings.validation import validate_production_config
from config.views import health, protected_media


BASE_DIR = Path(__file__).resolve().parent.parent


def test_development_does_not_enable_production_static_server():
    assert 'whitenoise.middleware.WhiteNoiseMiddleware' not in settings.MIDDLEWARE


def test_placeholder_secret_is_rejected():
    with pytest.raises(ImproperlyConfigured, match='placeholder'):
        validate_production_config(
            secret_key='change-this-to-a-long-random-secret-string',
            debug=False,
            allowed_hosts=['localhost'],
            csrf_trusted_origins=[],
            https=False,
        )


def test_short_secret_is_rejected():
    with pytest.raises(ImproperlyConfigured, match='too short'):
        validate_production_config(
            secret_key='x' * 20,
            debug=False,
            allowed_hosts=['localhost'],
            csrf_trusted_origins=[],
            https=False,
        )


def test_debug_true_is_rejected():
    with pytest.raises(ImproperlyConfigured, match='DEBUG must be False'):
        validate_production_config(
            secret_key='k' * 50,
            debug=True,
            allowed_hosts=['localhost'],
            csrf_trusted_origins=[],
            https=False,
        )


def test_wildcard_host_is_rejected():
    with pytest.raises(ImproperlyConfigured, match='must not contain'):
        validate_production_config(
            secret_key='k' * 50,
            debug=False,
            allowed_hosts=['localhost', '*'],
            csrf_trusted_origins=[],
            https=False,
        )


def test_empty_hosts_are_rejected():
    with pytest.raises(ImproperlyConfigured, match='ALLOWED_HOSTS is empty'):
        validate_production_config(
            secret_key='k' * 50,
            debug=False,
            allowed_hosts=[],
            csrf_trusted_origins=[],
            https=False,
        )


def test_csrf_origin_must_include_scheme():
    with pytest.raises(ImproperlyConfigured, match='CSRF_TRUSTED_ORIGINS'):
        validate_production_config(
            secret_key='k' * 50,
            debug=False,
            allowed_hosts=['localhost'],
            csrf_trusted_origins=['factory-pc'],
            https=False,
        )


def test_valid_production_config_is_accepted():
    validate_production_config(
        secret_key='k' * 50,
        debug=False,
        allowed_hosts=['localhost', '127.0.0.1'],
        csrf_trusted_origins=['http://127.0.0.1:8000'],
        https=False,
    )


def _production_env(tmp_path: Path, **overrides) -> dict:
    env = os.environ.copy()
    env['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'
    env['SECRET_KEY'] = 'k' * 50
    env['DEBUG'] = 'False'
    env['ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
    env['CSRF_TRUSTED_ORIGINS'] = 'http://127.0.0.1:8000,http://localhost:8000'
    env['FACTORYOPS_SQLITE_PATH'] = str(tmp_path / 'db.sqlite3')
    env['FACTORYOPS_MEDIA_ROOT'] = str(tmp_path / 'media')
    env['FACTORYOPS_STATIC_ROOT'] = str(tmp_path / 'staticfiles')
    env['FACTORYOPS_LOG_DIR'] = str(tmp_path / 'logs')
    env['FACTORYOPS_HTTPS'] = 'False'
    env.pop('FACTORYOPS_ENV_FILE', None)
    env.update(overrides)
    return env


def _run_production(tmp_path: Path, code: str, **overrides) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, '-c', code],
        cwd=BASE_DIR,
        env=_production_env(tmp_path, **overrides),
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_settings_import_succeeds(tmp_path):
    result = _run_production(tmp_path, 'import django; django.setup()')
    assert result.returncode == 0, result.stderr


def test_production_settings_reject_missing_secret(tmp_path):
    result = _run_production(tmp_path, 'import django; django.setup()', SECRET_KEY='')
    assert result.returncode != 0
    assert 'SECRET_KEY' in result.stderr
    assert 'k' * 50 not in result.stderr


def test_production_settings_reject_placeholder_secret(tmp_path):
    result = _run_production(
        tmp_path,
        'import django; django.setup()',
        SECRET_KEY='change-this-to-a-long-random-secret-string',
    )
    assert result.returncode != 0
    assert 'placeholder' in result.stderr


def test_production_settings_reject_wildcard_host(tmp_path):
    result = _run_production(
        tmp_path,
        'import django; django.setup()',
        ALLOWED_HOSTS='*',
    )
    assert result.returncode != 0
    assert 'ALLOWED_HOSTS' in result.stderr


def test_production_deploy_check_has_no_errors(tmp_path):
    result = _run_production(
        tmp_path,
        'import django; django.setup(); '
        'from django.core.management import call_command; '
        'call_command("check", deploy=True)',
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert 'k' * 50 not in result.stdout
    assert 'k' * 50 not in result.stderr


@pytest.mark.django_db
def test_health_is_public_and_hides_secrets(client):
    response = client.get(reverse('health'))
    body = response.content.decode()
    assert response.status_code == 200
    assert '"status": "ok"' in body or '"status":"ok"' in body.replace(' ', '')
    assert settings.SECRET_KEY not in body
    assert 'no-store' in response['Cache-Control']


@pytest.mark.django_db
def test_health_post_is_rejected(client):
    response = client.post(reverse('health'))
    assert response.status_code == 405


@pytest.mark.django_db
def test_health_database_failure_has_no_traceback(client, monkeypatch):
    def broken():
        raise RuntimeError('disk I/O secret-path /opt/plant')

    monkeypatch.setattr('config.views.database_ready', broken)
    response = client.get(reverse('health'))
    body = response.content.decode()
    assert response.status_code == 503
    assert body == '{"status": "unavailable"}'
    assert 'disk I/O' not in body
    assert 'secret-path' not in body
    assert settings.SECRET_KEY not in body


@pytest.mark.django_db
def test_health_does_not_bypass_dashboard_login(client):
    response = client.get(reverse('dashboard:operator'))
    assert response.status_code == 302
    assert '/accounts/login/' in response.url


@pytest.mark.django_db
def test_health_view_function_returns_ok():
    response = health(RequestFactory().get('/health/'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_protected_media_requires_login_and_serves_file(tmp_path, settings):
    media = tmp_path / 'media'
    media.mkdir()
    (media / 'note.txt').write_text('evidence', encoding='utf-8')
    settings.MEDIA_ROOT = media
    anonymous = RequestFactory().get('/media/note.txt')
    anonymous.user = AnonymousUser()
    denied = protected_media(anonymous, 'note.txt')
    assert denied.status_code == 302
    assert '/accounts/login/' in denied.url

    user = User.objects.create_user(
        username='media-reader',
        email='media@factoryops.local',
        password='Password123!',
        role=User.Role.SUPERVISOR,
    )
    allowed = RequestFactory().get('/media/note.txt')
    allowed.user = user
    response = protected_media(allowed, 'note.txt')
    assert response.status_code == 200
    with pytest.raises(Http404):
        protected_media(allowed, '../note.txt')


def test_log_setup_writes_a_rotating_file(tmp_path):
    env = os.environ.copy()
    env['LOG_DIR'] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'import logging, logging.config, os\n'
            'from pathlib import Path\n'
            'from config.settings.log_setup import build_logging\n'
            'target = Path(os.environ["LOG_DIR"])\n'
            'logging.config.dictConfig(build_logging(target, max_bytes=1024, backup_count=2))\n'
            'handler = logging.getLogger("factoryops").handlers[0]\n'
            'assert handler.maxBytes == 1024 and handler.backupCount == 2\n'
            'logging.getLogger("factoryops").info("factoryops-log-marker")\n',
        ],
        cwd=BASE_DIR,
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
    assert result.returncode == 0, result.stderr
    logfile = tmp_path / 'factoryops.log'
    assert logfile.is_file()
    assert 'factoryops-log-marker' in logfile.read_text(encoding='utf-8')


def test_templates_and_static_do_not_require_internet():
    roots = [BASE_DIR / 'templates', BASE_DIR / 'static']
    offenders = []
    for root in roots:
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            # XML namespace identifiers are not fetched at runtime.
            without_namespaces = text.replace('http://www.w3.org/', '')
            if 'http://' in without_namespaces or 'https://' in without_namespaces:
                offenders.append(str(path.relative_to(BASE_DIR)))
    assert offenders == []
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
