"""
Tests for Accounts App
"""

import pytest
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
