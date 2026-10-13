"""Seed sanitary-pad catalog rows for factories that already exist.

New factories are configured in Admin or via seed_sanitary_catalog().
"""

from decimal import Decimal

from django.db import migrations

SANITARY_PRODUCT_CODE = 'SANITARY-PADS'
VARIANTS = (
    ('STD', 'Standard Length'),
    ('THINS', 'Thins'),
    ('EXTRA', 'Extra Length'),
    ('MAXIS', "Maxi's"),
)
PACK_CODES = ("10's", "15's", "60's")


def seed_existing_factories(apps, schema_editor):
    Factory = apps.get_model('factories', 'Factory')
    Product = apps.get_model('catalog', 'Product')
    ProductVariant = apps.get_model('catalog', 'ProductVariant')
    Packaging = apps.get_model('catalog', 'Packaging')
    for factory in Factory.objects.all():
        product, _created = Product.objects.get_or_create(
            factory_id=factory.id,
            code=SANITARY_PRODUCT_CODE,
            defaults={'name': 'Sanitary Pads', 'is_active': True},
        )
        for code, name in VARIANTS:
            ProductVariant.objects.get_or_create(
                product_id=product.id,
                code=code,
                defaults={'name': name, 'is_active': True},
            )
        base, _created = Packaging.objects.get_or_create(
            factory_id=factory.id,
            code="10's",
            defaults={
                'name': "10's",
                'base_unit_quantity': Decimal('10'),
                'individual_unit_label': 'pads',
                'is_active': True,
            },
        )
        Packaging.objects.get_or_create(
            factory_id=factory.id,
            code="15's",
            defaults={
                'name': "15's",
                'contains_id': base.id,
                'quantity_per': Decimal('15'),
                'individual_unit_label': 'pads',
                'is_active': True,
            },
        )
        Packaging.objects.get_or_create(
            factory_id=factory.id,
            code="60's",
            defaults={
                'name': "60's",
                'contains_id': base.id,
                'quantity_per': Decimal('60'),
                'individual_unit_label': 'pads',
                'is_active': True,
            },
        )


def unseed(apps, schema_editor):
    Product = apps.get_model('catalog', 'Product')
    ProductVariant = apps.get_model('catalog', 'ProductVariant')
    Packaging = apps.get_model('catalog', 'Packaging')
    ProductVariant.objects.filter(product__code=SANITARY_PRODUCT_CODE, code__in=[code for code, _name in VARIANTS]).delete()
    Product.objects.filter(code=SANITARY_PRODUCT_CODE).delete()
    Packaging.objects.filter(code__in=("15's", "60's")).delete()
    Packaging.objects.filter(code="10's").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial_catalog'),
        ('factories', '0002_productionline_code'),
    ]

    operations = [
        migrations.RunPython(seed_existing_factories, unseed),
    ]
