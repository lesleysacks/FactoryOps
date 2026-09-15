"""
Tests for Factories App
"""

import pytest
from apps.factories.models import Factory, ProductionLine


@pytest.mark.django_db
def test_factory_creation():
    factory = Factory.objects.create(name="North Plant", location="Building 4")
    assert factory.name == "North Plant"
    assert factory.is_active is True
    assert str(factory) == "North Plant"


@pytest.mark.django_db
def test_production_line_relation(factory):
    line = ProductionLine.objects.create(
        factory=factory,
        name="Packaging Line A",
        code="PKG-A"
    )
    assert line.factory == factory
    assert str(line) == "Main Factory - Packaging Line A (PKG-A)"
    assert factory.lines.count() == 1
    assert factory.lines.first() == line
