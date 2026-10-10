"""
FactoryOps Catalog — product, variant, and packaging master data.

Packaging conversions are data. Nothing in this app hardcodes a pack size.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

MAX_PACKAGING_DEPTH = 20


class Product(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='products',
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ('factory', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'code'],
                name='unique_product_code_per_factory',
            ),
        ]

    def __str__(self):
        return f'{self.code} — {self.name}'

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip()
        if self.name:
            self.name = self.name.strip()
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot create a product for an inactive factory.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='variants',
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    finished_good = models.ForeignKey(
        'production.FinishedGood',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='product_variants',
        help_text='Optional link into the finished-goods warehouse chain.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
        ordering = ('product', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'code'],
                name='unique_variant_code_per_product',
            ),
        ]

    def __str__(self):
        return f'{self.product.code} — {self.name}'

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip()
        if self.name:
            self.name = self.name.strip()
        if self.finished_good_id and self.product_id:
            if self.finished_good.factory_id != self.product.factory_id:
                raise ValidationError({
                    'finished_good': (
                        'Finished good must belong to the same factory as the product.'
                    ),
                })
        if self._state.adding and self.product_id and not self.product.is_active:
            raise ValidationError({
                'product': 'Cannot add a variant to an inactive product.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Packaging(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='packaging',
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    contains = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='contained_by',
        help_text='Packaging this one is composed of. Empty means this is a base pack.',
    )
    quantity_per = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='How many of the contained packaging are in one of this packaging.',
    )
    base_unit_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Individual units in a base pack. Required only when this pack contains nothing else.',
    )
    individual_unit_label = models.CharField(
        max_length=50,
        blank=True,
        help_text='Display label for one individual unit, for example pads.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Packaging'
        verbose_name_plural = 'Packaging'
        ordering = ('factory', 'code')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'code'],
                name='unique_packaging_code_per_factory',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        contains__isnull=True,
                        base_unit_quantity__isnull=False,
                        quantity_per__isnull=True,
                    )
                    | models.Q(
                        contains__isnull=False,
                        quantity_per__isnull=False,
                        base_unit_quantity__isnull=True,
                    )
                ),
                name='packaging_base_or_composed',
            ),
        ]

    def __str__(self):
        return f'{self.code} — {self.name}'

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip()
        if self.name:
            self.name = self.name.strip()
        if self.individual_unit_label:
            self.individual_unit_label = self.individual_unit_label.strip()
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot create packaging for an inactive factory.',
            })
        if self.contains_id is None:
            if self.base_unit_quantity is None:
                raise ValidationError({
                    'base_unit_quantity': 'A base pack requires a base unit quantity.',
                })
            if self.quantity_per is not None:
                raise ValidationError({
                    'quantity_per': 'A base pack cannot set quantity per.',
                })
        else:
            if self.quantity_per is None:
                raise ValidationError({
                    'quantity_per': 'Composed packaging requires quantity per.',
                })
            if self.base_unit_quantity is not None:
                raise ValidationError({
                    'base_unit_quantity': 'Composed packaging cannot set a base unit quantity.',
                })
            if self.quantity_per <= 0:
                raise ValidationError({
                    'quantity_per': 'Quantity per must be greater than zero.',
                })
            if self.contains.factory_id != self.factory_id:
                raise ValidationError({
                    'contains': 'Contained packaging must belong to the same factory.',
                })
            if self._chain_has_cycle():
                raise ValidationError({
                    'contains': 'Packaging composition cannot contain a cycle.',
                })
        if self.base_unit_quantity is not None and self.base_unit_quantity <= 0:
            raise ValidationError({
                'base_unit_quantity': 'Base unit quantity must be greater than zero.',
            })

    def _chain_has_cycle(self):
        seen = set()
        if self.pk:
            seen.add(self.pk)
        current_id = self.contains_id
        depth = 0
        while current_id:
            depth += 1
            if depth > MAX_PACKAGING_DEPTH or current_id in seen:
                return True
            seen.add(current_id)
            current_id = (
                Packaging.objects.filter(pk=current_id)
                .values_list('contains_id', flat=True)
                .first()
            )
        return False

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
