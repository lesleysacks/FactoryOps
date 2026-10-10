"""
FactoryOps Test Fixtures and Pytest Configuration
"""

import pytest
from apps.accounts.models import User
from apps.factories.models import Factory, ProductionLine
from apps.machines.models import Machine
from apps.materials.models import Material, MaterialCategory, UnitOfMeasure


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
def unit_of_measure(db):
    return UnitOfMeasure.objects.create(name='Kilogram', symbol='kg')


@pytest.fixture
def material_category(db, factory):
    return MaterialCategory.objects.create(
        factory=factory,
        name='Raw Materials',
    )


@pytest.fixture
def material(db, factory, material_category, unit_of_measure):
    return Material.objects.create(
        factory=factory,
        name='SAP',
        code='SAP-001',
        category=material_category,
        unit=unit_of_measure,
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
