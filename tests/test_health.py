"""The health check reports availability and nothing else."""

import pytest
from django.test import Client


@pytest.mark.django_db
def test_health_ok_has_no_secrets():
    response = Client().get('/health/')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert 'no-store' in response['Cache-Control']
    body = response.content.decode('utf-8')
    assert 'SECRET' not in body
    assert 'sqlite' not in body.lower()


@pytest.mark.django_db
def test_health_database_failure_is_generic(monkeypatch):
    def explode():
        raise RuntimeError('C:\\FactoryOps\\secret\\db.sqlite3')

    monkeypatch.setattr('config.health.connection.cursor', explode)
    response = Client().get('/health/')
    assert response.status_code == 503
    assert response.json() == {'status': 'unavailable'}
    body = response.content.decode('utf-8')
    assert 'secret' not in body
    assert 'RuntimeError' not in body


def test_health_rejects_post():
    response = Client().post('/health/')
    assert response.status_code == 405
