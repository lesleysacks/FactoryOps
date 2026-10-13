"""Catalog isolation, packaging conversion, and invalid packaging."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.catalog.models import Packaging, Product, ProductVariant
from apps.catalog.services import individual_units, seed_sanitary_catalog
from apps.factories.models import Factory


@pytest.fixture
def other_factory(db):
    return Factory.objects.create(name='Other Plant', location='Building 2')


def test_seed_sanitary_units(factory):
    seed_sanitary_catalog(factory)
    packs = {
        pack.code: pack
        for pack in Packaging.objects.filter(factory=factory)
    }
    assert individual_units(packs["10's"]) == Decimal('10.000')
    assert individual_units(packs["15's"]) == Decimal('150.000')
    assert individual_units(packs["60's"]) == Decimal('600.000')
    product = Product.objects.get(factory=factory, code='SANITARY-PADS')
    assert product.variants.count() == 4


def test_seed_is_idempotent(factory):
    seed_sanitary_catalog(factory)
    seed_sanitary_catalog(factory)
    assert Product.objects.filter(factory=factory, code='SANITARY-PADS').count() == 1
    assert Packaging.objects.filter(factory=factory).count() == 3


def test_cross_factory_packaging_rejected(factory, other_factory):
    base = Packaging.objects.create(
        factory=factory,
        code="10's",
        name="10's",
        base_unit_quantity=Decimal('10'),
    )
    with pytest.raises(ValidationError):
        Packaging.objects.create(
            factory=other_factory,
            code="15's",
            name="15's",
            contains=base,
            quantity_per=Decimal('15'),
        )


def test_variant_finished_good_must_match_factory(factory, other_factory):
    from apps.production.models import FinishedGood

    product = Product.objects.create(factory=factory, code='PADS', name='Pads')
    other_good = FinishedGood.objects.create(
        factory=other_factory,
        code='FG-1',
        name='Other good',
    )
    with pytest.raises(ValidationError):
        ProductVariant.objects.create(
            product=product,
            code='STD',
            name='Standard',
            finished_good=other_good,
        )


def test_base_pack_rejects_quantity_per(factory):
    with pytest.raises(ValidationError):
        Packaging.objects.create(
            factory=factory,
            code='BASE',
            name='Base',
            base_unit_quantity=Decimal('10'),
            quantity_per=Decimal('2'),
        )


def test_base_pack_requires_base_quantity(factory):
    with pytest.raises(ValidationError):
        Packaging.objects.create(factory=factory, code='BASE', name='Base')


def test_composed_pack_rejects_base_quantity(factory):
    base = Packaging.objects.create(
        factory=factory,
        code='BASE',
        name='Base',
        base_unit_quantity=Decimal('10'),
    )
    with pytest.raises(ValidationError):
        Packaging.objects.create(
            factory=factory,
            code='BOX',
            name='Box',
            contains=base,
            quantity_per=Decimal('4'),
            base_unit_quantity=Decimal('40'),
        )


def test_non_positive_base_quantity_rejected(factory):
    with pytest.raises(ValidationError):
        Packaging.objects.create(
            factory=factory,
            code='BASE',
            name='Base',
            base_unit_quantity=Decimal('0'),
        )


def test_packaging_cycle_rejected(factory):
    base = Packaging.objects.create(
        factory=factory,
        code='BASE',
        name='Base',
        base_unit_quantity=Decimal('10'),
    )
    outer = Packaging.objects.create(
        factory=factory,
        code='OUTER',
        name='Outer',
        contains=base,
        quantity_per=Decimal('2'),
    )
    base.contains = outer
    base.quantity_per = Decimal('2')
    base.base_unit_quantity = None
    with pytest.raises(ValidationError):
        base.save()


def test_individual_units_rejects_in_memory_cycle():
    outer = Packaging(code='OUTER', quantity_per=Decimal('2'))
    inner = Packaging(code='INNER', quantity_per=Decimal('2'))
    outer.contains = inner
    inner.contains = outer
    with pytest.raises(ValidationError):
        individual_units(outer)
