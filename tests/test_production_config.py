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
