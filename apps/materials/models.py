"""
FactoryOps Materials — Master Data Models
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class UnitOfMeasure(models.Model):
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Unit of Measure'
        verbose_name_plural = 'Units of Measure'
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class MaterialCategory(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.CASCADE,
        related_name='material_categories',
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material Category'
        verbose_name_plural = 'Material Categories'
        ordering = ('factory', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'name'],
                name='unique_material_category_per_factory',
            ),
        ]

    def __str__(self):
        return f"{self.factory.name} — {self.name}"


class Material(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.CASCADE,
        related_name='materials',
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50)
    category = models.ForeignKey(
        MaterialCategory,
        on_delete=models.PROTECT,
        related_name='materials',
    )
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='materials',
    )
    is_active = models.BooleanField(default=True)
    minimum_stock_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Minimum stock level before low-stock warnings apply.',
    )
    target_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Optional target stock level for operational reference.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('factory', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'code'],
                name='unique_material_code_per_factory',
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def clean(self):
        super().clean()
        if self.category_id and self.factory_id:
            if self.category.factory_id != self.factory_id:
                raise ValidationError({
                    'category': 'Category must belong to the same factory as the material.',
                })
        if self.target_stock is not None and self.target_stock < Decimal('0'):
            raise ValidationError({
                'target_stock': 'Target stock cannot be negative.',
            })
        if self.minimum_stock_threshold < Decimal('0'):
            raise ValidationError({
                'minimum_stock_threshold': 'Minimum stock threshold cannot be negative.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StockRecord(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='stock_records',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='stock_records',
    )
    recording_date = models.DateField()
    opening_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Counted quantity at the start of the recording date.',
    )
    closing_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Counted quantity at the end of the recording date. Leave blank if closing has not been recorded yet.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Stock Record'
        verbose_name_plural = 'Stock Records'
        ordering = ('-recording_date', 'factory', 'material')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'material', 'recording_date'],
                name='unique_stock_record_per_factory_material_date',
            ),
            models.CheckConstraint(
                condition=models.Q(opening_quantity__gte=0),
                name='stock_record_opening_quantity_non_negative',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(closing_quantity__gte=0)
                    | models.Q(closing_quantity__isnull=True)
                ),
                name='stock_record_closing_quantity_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.factory.name} — {self.material.code} — {self.recording_date}"

    def clean(self):
        super().clean()
        if self.factory_id and self.material_id:
            if self.material.factory_id != self.factory_id:
                raise ValidationError({
                    'material': 'Material must belong to the same factory as the stock record.',
                })
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot record stock for an inactive material.',
            })
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot record stock for an inactive factory.',
            })
        if self.opening_quantity is not None and self.opening_quantity < Decimal('0'):
            raise ValidationError({
                'opening_quantity': 'Opening quantity cannot be negative.',
            })
        if self.closing_quantity is not None and self.closing_quantity < Decimal('0'):
            raise ValidationError({
                'closing_quantity': 'Closing quantity cannot be negative.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MaterialBatch(models.Model):
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='batches',
    )
    lot_number = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material Batch'
        verbose_name_plural = 'Material Batches'
        ordering = ('material', 'lot_number')
        constraints = [
            models.UniqueConstraint(
                fields=['material', 'lot_number'],
                name='unique_lot_number_per_material',
            ),
        ]

    def __str__(self):
        return f"{self.material.code} — {self.lot_number}"

    def clean(self):
        super().clean()
        if self.lot_number:
            self.lot_number = self.lot_number.strip()
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot create a batch for an inactive material.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MaterialAddition(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='material_additions',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='additions',
    )
    batch = models.ForeignKey(
        MaterialBatch,
        on_delete=models.PROTECT,
        related_name='additions',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of material received. Must be greater than zero.',
    )
    added_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this material physically entered the factory.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material Addition'
        verbose_name_plural = 'Material Additions'
        ordering = ('-added_at', 'factory', 'material')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='material_addition_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.factory.name} — {self.material.code} — "
            f"{self.quantity} — {self.batch.lot_number}"
        )

    def clean(self):
        super().clean()
        if self.factory_id and self.material_id:
            if self.material.factory_id != self.factory_id:
                raise ValidationError({
                    'material': 'Material must belong to the same factory as the addition.',
                })
        if self.batch_id and self.material_id:
            if self.batch.material_id != self.material_id:
                raise ValidationError({
                    'batch': 'Batch must belong to the same material as the addition.',
                })
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot record an addition for an inactive material.',
            })
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot record an addition for an inactive factory.',
            })
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MaterialConsumption(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='material_consumptions',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='consumptions',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of material consumed. Must be greater than zero.',
    )
    consumed_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this material was physically used.',
    )
    production_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text='Optional free-text production activity reference. Prefer production_run for traceability.',
    )
    production_run = models.ForeignKey(
        'production.ProductionRun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='material_consumptions',
        help_text='Optional production run this consumption belongs to.',
    )
    batch = models.ForeignKey(
        MaterialBatch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='consumptions',
        help_text='Lot consumed. Required for operator-recorded consumption.',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_consumptions',
        help_text='User who recorded the consumption. Set server-side.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material Consumption'
        verbose_name_plural = 'Material Consumptions'
        ordering = ('-consumed_at', 'factory', 'material')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='material_consumption_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        base = f"{self.factory.name} — {self.material.code} — {self.quantity}"
        if self.production_reference:
            return f"{base} — {self.production_reference}"
        return base

    def clean(self):
        super().clean()
        if self.production_reference:
            self.production_reference = self.production_reference.strip()
        if self.factory_id and self.material_id:
            if self.material.factory_id != self.factory_id:
                raise ValidationError({
                    'material': 'Material must belong to the same factory as the consumption.',
                })
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot record consumption for an inactive material.',
            })
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot record consumption for an inactive factory.',
            })
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })
        if self.production_run_id and self.factory_id:
            if self.production_run.factory_id != self.factory_id:
                raise ValidationError({
                    'production_run': 'Production run must belong to the same factory as the consumption.',
                })
        if self.batch_id and self.material_id:
            if self.batch.material_id != self.material_id:
                raise ValidationError({
                    'batch': 'Batch must belong to the same material as the consumption.',
                })
        if self.batch_id and self.factory_id:
            if self.batch.material.factory_id != self.factory_id:
                raise ValidationError({
                    'batch': 'Batch must belong to the same factory as the consumption.',
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MaterialWaste(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='material_wastes',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='wastes',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of material lost as waste. Must be greater than zero.',
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this waste occurred.',
    )
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material Waste'
        verbose_name_plural = 'Material Waste'
        ordering = ('-occurred_at', 'factory', 'material')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='material_waste_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.factory.name} — {self.material.code} — "
            f"{self.quantity} — {self.reason}"
        )

    def clean(self):
        super().clean()
        if self.reason:
            self.reason = self.reason.strip()
        if self.factory_id and self.material_id:
            if self.material.factory_id != self.factory_id:
                raise ValidationError({
                    'material': 'Material must belong to the same factory as the waste record.',
                })
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot record waste for an inactive material.',
            })
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot record waste for an inactive factory.',
            })
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MaterialScrap(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='material_scraps',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='scraps',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of material scrapped. Must be greater than zero.',
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this scrap occurred.',
    )
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material Scrap'
        verbose_name_plural = 'Material Scrap'
        ordering = ('-occurred_at', 'factory', 'material')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='material_scrap_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.factory.name} — {self.material.code} — "
            f"{self.quantity} — {self.reason}"
        )

    def clean(self):
        super().clean()
        if self.reason:
            self.reason = self.reason.strip()
        if self.factory_id and self.material_id:
            if self.material.factory_id != self.factory_id:
                raise ValidationError({
                    'material': 'Material must belong to the same factory as the scrap record.',
                })
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot record scrap for an inactive material.',
            })
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot record scrap for an inactive factory.',
            })
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StockReconciliation(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='stock_reconciliations',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='stock_reconciliations',
    )
    reconciliation_date = models.DateField()
    notes = models.TextField(blank=True)
    expected_closing_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text='Opening + additions − consumption − waste − scrap.',
    )
    actual_closing_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text='Copied from the matching stock record closing quantity.',
    )
    variance_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text='Actual closing minus expected closing. Positive means more stock than expected.',
    )
    calculated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Stock Reconciliation'
        verbose_name_plural = 'Stock Reconciliations'
        ordering = ('-reconciliation_date', 'factory', 'material')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'material', 'reconciliation_date'],
                name='unique_stock_reconciliation_per_factory_material_date',
            ),
        ]

    def __str__(self):
        return f"{self.factory.name} — {self.material.code} — {self.reconciliation_date}"

    def clean(self):
        super().clean()
        if self.factory_id and self.material_id:
            if self.material.factory_id != self.factory_id:
                raise ValidationError({
                    'material': 'Material must belong to the same factory as the reconciliation.',
                })
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot create a reconciliation for an inactive material.',
            })
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot create a reconciliation for an inactive factory.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def calculate(self):
        from apps.materials.services import reconcile_stock

        return reconcile_stock(self)
