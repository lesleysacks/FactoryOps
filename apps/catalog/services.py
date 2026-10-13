"""
FactoryOps Catalog — packaging conversion.

individual_units is the only place that converts a pack into individual units.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from apps.catalog.models import MAX_PACKAGING_DEPTH, Packaging, Product, ProductVariant

ZERO = Decimal('0')
QUANTITY_QUANTUM = Decimal('0.001')

SANITARY_PRODUCT_CODE = 'SANITARY-PADS'
SANITARY_VARIANTS = (
    ('STD', 'Standard Length'),
    ('THINS', 'Thins'),
    ('EXTRA', 'Extra Length'),
    ('MAXIS', "Maxi's"),
)


def _as_quantity(value):
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def individual_units(packaging, _memo=None, _seen=None):
    """Return how many individual units one of this packaging represents."""
    if packaging is None:
        raise ValidationError('Packaging is required.')
    memo = {} if _memo is None else _memo
    seen = set() if _seen is None else _seen
    key = packaging.pk or id(packaging)
    if key in memo:
        return memo[key]
    if key in seen or len(seen) > MAX_PACKAGING_DEPTH:
        raise ValidationError('Packaging composition contains a cycle.')
    seen.add(key)

    contains_id = packaging.contains_id
    if contains_id is None and packaging.contains is None:
        if packaging.base_unit_quantity is None:
            raise ValidationError('Base packaging requires a base unit quantity.')
        result = _as_quantity(packaging.base_unit_quantity)
    else:
        if packaging.quantity_per is None:
            raise ValidationError('Composed packaging requires quantity per.')
        parent = packaging.contains
        if parent is None:
            parent = Packaging.objects.get(pk=contains_id)
        result = _as_quantity(
            packaging.quantity_per * individual_units(parent, memo, seen)
        )
    memo[key] = result
    return result


def seed_sanitary_catalog(factory):
    """Create the sanitary-pad product, four variants, and 10's / 15's / 60's packs.

    Idempotent per factory. Another factory can define different products in Admin
    without any code change.
    """
    product, _created = Product.objects.get_or_create(
        factory=factory,
        code=SANITARY_PRODUCT_CODE,
        defaults={'name': 'Sanitary Pads', 'is_active': True},
    )
    for code, name in SANITARY_VARIANTS:
        ProductVariant.objects.get_or_create(
            product=product,
            code=code,
            defaults={'name': name, 'is_active': True},
        )
    base, _created = Packaging.objects.get_or_create(
        factory=factory,
        code="10's",
        defaults={
            'name': "10's",
            'base_unit_quantity': Decimal('10'),
            'individual_unit_label': 'pads',
            'is_active': True,
        },
    )
    Packaging.objects.get_or_create(
        factory=factory,
        code="15's",
        defaults={
            'name': "15's",
            'contains': base,
            'quantity_per': Decimal('15'),
            'individual_unit_label': 'pads',
            'is_active': True,
        },
    )
    Packaging.objects.get_or_create(
        factory=factory,
        code="60's",
        defaults={
            'name': "60's",
            'contains': base,
            'quantity_per': Decimal('60'),
            'individual_unit_label': 'pads',
            'is_active': True,
        },
    )
    return product
