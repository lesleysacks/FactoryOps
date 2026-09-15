"""
FactoryOps Test Fixtures and Pytest Configuration
"""

import pytest
from apps.accounts.models import User
from apps.factories.models import Factory, ProductionLine
from apps.machines.models import Machine


@pytest.fixture
def factory(db):
    return Factory.objects.create(
        name="Main Factory",
        location="Sector A"
    )


@pytest.fixture
def production_line(db, factory):
    return ProductionLine.objects.create(
        factory=factory,
        name="Line 1",
        code="L1"
    )


@pytest.fixture
def user(db, factory):
    return User.objects.create_user(
        username="operator1",
        email="op1@factoryops.local",
        password="Password123!",
        role=User.Role.OPERATOR,
        factory=factory
    )
