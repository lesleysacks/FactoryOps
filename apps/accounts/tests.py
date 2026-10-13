"""
Tests for Accounts App
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.accounts.models import User
from apps.factories.models import Factory


@pytest.mark.django_db
def test_create_user():
    user = User.objects.create_user(
        username="john_doe",
        email="john@example.com",
        password="secretpassword",
        role=User.Role.SUPERVISOR,
        employee_id="EMP-001"
    )
    assert user.username == "john_doe"
    assert user.role == User.Role.SUPERVISOR
    assert user.employee_id == "EMP-001"
    assert str(user) == "john_doe (Supervisor)"


@pytest.mark.django_db
def test_create_superuser():
    user = User.objects.create_superuser(
        username="admin_user",
        email="admin@example.com",
        password="adminpassword"
    )
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.role == User.Role.ADMIN


# ---------------------------------------------------------------------------
# Login UI (animated experience) — structure & behaviour only, never timing.
# ---------------------------------------------------------------------------

@pytest.fixture
def login_url():
    return reverse('accounts:login')


@pytest.mark.django_db
def test_login_page_returns_200(client, login_url):
    assert client.get(login_url).status_code == 200


@pytest.mark.django_db
def test_login_page_shows_factoryops_branding(client, login_url):
    content = client.get(login_url).content
    assert b'FactoryOps' in content
    # Contiguous product phrase must remain present (escaped) for branding + a11y.
    assert b'Production &amp; Inventory Intelligence' in content


@pytest.mark.django_db
def test_login_page_has_split_product_wordmark(client, login_url):
    content = client.get(login_url).content.decode()
    assert 'auth-product' in content
    assert 'Production &amp; Inventory' in content
    assert '>Intelligence<' in content


@pytest.mark.django_db
def test_login_page_preserves_csrf_protection(client, login_url):
    content = client.get(login_url).content
    assert b'csrfmiddlewaretoken' in content


@pytest.mark.django_db
def test_login_page_has_username_and_password_fields(client, login_url):
    content = client.get(login_url).content.decode()
    assert 'name="username"' in content
    assert 'name="password"' in content
    assert 'Enter your username' in content
    assert 'Enter your password' in content


@pytest.mark.django_db
def test_login_page_has_submit_button(client, login_url):
    content = client.get(login_url).content.decode()
    assert 'data-auth-submit' in content
    assert 'Sign in' in content


@pytest.mark.django_db
def test_login_page_has_honest_system_status(client, login_url):
    content = client.get(login_url).content.decode()
    assert 'data-auth-status' in content
    assert 'System ready' in content
    # Honest UI: must not claim states the app cannot establish.
    for claim in ('Connected', 'Authenticated', 'Secure', 'Online'):
        assert claim not in content


@pytest.mark.django_db
def test_invalid_login_shows_accessible_error(client, login_url):
    response = client.post(
        login_url,
        {'username': 'nobody', 'password': 'wrong-password', 'next': ''},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert 'not recognised' in content
    assert 'role="alert"' in content


@pytest.mark.django_db
def test_valid_login_redirects_to_dashboard(client, login_url, user):
    response = client.post(
        login_url,
        {'username': user.username, 'password': 'Password123!', 'next': '/dashboard/'},
    )
    assert response.status_code == 302
    assert response.url == '/dashboard/'


@pytest.mark.django_db
def test_login_page_includes_favicon_branding(client, login_url):
    content = client.get(login_url).content.decode()
    assert 'img/favicon/favicon.ico' in content
    assert 'img/favicon/favicon.svg' in content


def test_stylesheet_supports_reduced_motion():
    css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'factoryops.css').read_text()
    assert 'prefers-reduced-motion: reduce' in css
