"""
FactoryOps Production — Production Run and Output Models
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class ProductionRunStatus(models.TextChoices):
    PLANNED = 'PLANNED', 'Planned'
    IN_PROGRESS = 'IN_PROGRESS', 'In progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class ProductionRun(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='production_runs',
    )
    production_line = models.ForeignKey(
        'factories.ProductionLine',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='production_runs',
        help_text='Line this run was started on. Required for operator-started runs.',
    )
    machine = models.ForeignKey(
        'machines.Machine',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='production_runs',
        help_text='Machine this run was started on. Required for operator-started runs.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_runs',
        help_text='Operator who started the run. Set server-side.',
    )
    reference = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=ProductionRunStatus.choices,
        default=ProductionRunStatus.PLANNED,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Run'
        verbose_name_plural = 'Production Runs'
        ordering = ('-created_at', 'factory', 'reference')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'reference'],
                name='unique_production_run_reference_per_factory',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(ended_at__isnull=True)
                    | (
                        models.Q(started_at__isnull=False)
                        & models.Q(ended_at__gte=models.F('started_at'))
                    )
                ),
                name='production_run_ended_at_not_before_started_at',
            ),
        ]

    def __str__(self):
        return f"{self.factory.name} — {self.reference}"

    def clean(self):
        super().clean()
        if self.reference:
            self.reference = self.reference.strip()
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot create a production run for an inactive factory.',
            })
        if self.ended_at is not None and self.started_at is None:
            raise ValidationError({
                'ended_at': 'Ended at requires a started at timestamp.',
            })
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at < self.started_at
        ):
            raise ValidationError({
                'ended_at': 'Ended at cannot be before started at.',
            })
        if self.status == ProductionRunStatus.IN_PROGRESS and self.started_at is None:
            raise ValidationError({
                'started_at': 'An in-progress run must have a started at timestamp.',
            })
        if self.status == ProductionRunStatus.COMPLETED:
            if self.started_at is None:
                raise ValidationError({
                    'started_at': 'A completed run must have a started at timestamp.',
                })
            if self.ended_at is None:
                raise ValidationError({
                    'ended_at': 'A completed run must have an ended at timestamp.',
                })
        if self.production_line_id and self.factory_id:
            if self.production_line.factory_id != self.factory_id:
                raise ValidationError({
                    'production_line': 'Production line must belong to the same factory as the run.',
                })
        if self.machine_id and self.production_line_id:
            if self.machine.production_line_id != self.production_line_id:
                raise ValidationError({
                    'machine': 'Machine must belong to the selected production line.',
                })
        if self.machine_id and self.factory_id:
            if self.machine.production_line.factory_id != self.factory_id:
                raise ValidationError({
                    'machine': 'Machine must belong to the same factory as the run.',
                })
        if self._state.adding and self.machine_id and not self.machine.is_active:
            raise ValidationError({
                'machine': 'Cannot start a production run on an inactive machine.',
            })
        if (
            self._state.adding
            and self.production_line_id
            and not self.production_line.is_active
        ):
            raise ValidationError({
                'production_line': 'Cannot start a production run on an inactive production line.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProductionRunMaterialState(models.Model):
    """Snapshot of material loaded on the machine and spare beside it."""

    production_run = models.ForeignKey(
        ProductionRun,
        on_delete=models.PROTECT,
        related_name='material_states',
    )
    material = models.ForeignKey(
        'materials.Material',
        on_delete=models.PROTECT,
        related_name='run_material_states',
    )
    roll_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Quantity currently loaded on the machine. May be zero.',
    )
    spare_roll_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Spare quantity available beside the machine. May be zero.',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_run_material_states',
        help_text='User who recorded this snapshot. Set server-side.',
    )
    recorded_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this machine material state was recorded.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Run Material State'
        verbose_name_plural = 'Production Run Material States'
        ordering = ('-recorded_at', 'production_run', 'material')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(roll_quantity__gte=0),
                name='production_run_material_state_roll_quantity_not_negative',
            ),
            models.CheckConstraint(
                condition=models.Q(spare_roll_quantity__gte=0),
                name='production_run_material_state_spare_quantity_not_negative',
            ),
        ]

    def __str__(self):
        return (
            f"{self.production_run.reference} — {self.material.code} — "
            f"roll {self.roll_quantity} / spare {self.spare_roll_quantity}"
        )

    def clean(self):
        super().clean()
        if self.production_run_id and self.material_id:
            if self.material.factory_id != self.production_run.factory_id:
                raise ValidationError({
                    'material': 'Material must belong to the same factory as the production run.',
                })
        if self._state.adding and self.material_id and not self.material.is_active:
            raise ValidationError({
                'material': 'Cannot record material state for an inactive material.',
            })
        if self.roll_quantity is not None and self.roll_quantity < Decimal('0'):
            raise ValidationError({
                'roll_quantity': 'Roll quantity cannot be negative.',
            })
        if self.spare_roll_quantity is not None and self.spare_roll_quantity < Decimal('0'):
            raise ValidationError({
                'spare_roll_quantity': 'Spare roll quantity cannot be negative.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FinishedGood(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='finished_goods',
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Finished Good'
        verbose_name_plural = 'Finished Goods'
        ordering = ('factory', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'code'],
                name='unique_finished_good_code_per_factory',
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip()
        if self.name:
            self.name = self.name.strip()
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot create a finished good for an inactive factory.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProductionOutput(models.Model):
    production_run = models.ForeignKey(
        ProductionRun,
        on_delete=models.PROTECT,
        related_name='outputs',
    )
    output_name = models.CharField(max_length=150, blank=True)
    finished_good = models.ForeignKey(
        'FinishedGood',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='outputs',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity produced. Must be greater than zero.',
    )
    recorded_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this output was recorded.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Output'
        verbose_name_plural = 'Production Outputs'
        ordering = ('-recorded_at', 'production_run')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='production_output_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        label = self.output_name
        if not label and self.finished_good_id:
            label = self.finished_good.code
        return (
            f"{self.production_run.reference} — {label} — {self.quantity}"
        )

    def clean(self):
        super().clean()
        if self.output_name:
            self.output_name = self.output_name.strip()
        if not self.output_name and not self.finished_good_id:
            raise ValidationError(
                'Provide an output name or a finished good.'
            )
        if self.finished_good_id and self.production_run_id:
            if self.finished_good.factory_id != self.production_run.factory_id:
                raise ValidationError({
                    'finished_good': 'Finished good must belong to the same factory as the production run.',
                })
        if (
            self._state.adding
            and self.finished_good_id
            and not self.finished_good.is_active
        ):
            raise ValidationError({
                'finished_good': 'Cannot record output for an inactive finished good.',
            })
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProductionReject(models.Model):
    production_run = models.ForeignKey(
        ProductionRun,
        on_delete=models.PROTECT,
        related_name='rejects',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of production output rejected. Must be greater than zero.',
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this reject occurred.',
    )
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Reject'
        verbose_name_plural = 'Production Rejects'
        ordering = ('-occurred_at', 'production_run')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='production_reject_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.production_run.reference} — {self.quantity} — {self.reason}"
        )

    def clean(self):
        super().clean()
        if self.reason:
            self.reason = self.reason.strip()
        if (
            self._state.adding
            and self.production_run_id
            and not self.production_run.factory.is_active
        ):
            raise ValidationError({
                'production_run': 'Cannot record a reject for an inactive factory.',
            })
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Warehouse(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='warehouses',
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Warehouse'
        verbose_name_plural = 'Warehouses'
        ordering = ('factory', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'code'],
                name='unique_warehouse_code_per_factory',
            ),
        ]

    def __str__(self):
        return f"{self.factory.name} — {self.code}"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip()
        if self.name:
            self.name = self.name.strip()
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot create a warehouse for an inactive factory.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


def _validate_warehouse_finished_good(warehouse, finished_good, *, adding):
    if warehouse and finished_good:
        if warehouse.factory_id != finished_good.factory_id:
            raise ValidationError({
                'finished_good': 'Finished good must belong to the same factory as the warehouse.',
            })
    if adding:
        if warehouse and not warehouse.is_active:
            raise ValidationError({
                'warehouse': 'Cannot record stock against an inactive warehouse.',
            })
        if finished_good and not finished_good.is_active:
            raise ValidationError({
                'finished_good': 'Cannot record stock against an inactive finished good.',
            })


class FinishedGoodStockRecord(models.Model):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='stock_records',
    )
    finished_good = models.ForeignKey(
        FinishedGood,
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
        verbose_name = 'Finished Good Stock Record'
        verbose_name_plural = 'Finished Good Stock Records'
        ordering = ('-recording_date', 'warehouse', 'finished_good')
        constraints = [
            models.UniqueConstraint(
                fields=['warehouse', 'finished_good', 'recording_date'],
                name='unique_fg_stock_record_per_warehouse_item_date',
            ),
            models.CheckConstraint(
                condition=models.Q(opening_quantity__gte=0),
                name='fg_stock_record_opening_quantity_non_negative',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(closing_quantity__gte=0)
                    | models.Q(closing_quantity__isnull=True)
                ),
                name='fg_stock_record_closing_quantity_non_negative',
            ),
        ]

    def __str__(self):
        return (
            f"{self.warehouse.code} — {self.finished_good.code} — {self.recording_date}"
        )

    def clean(self):
        super().clean()
        _validate_warehouse_finished_good(
            self.warehouse if self.warehouse_id else None,
            self.finished_good if self.finished_good_id else None,
            adding=self._state.adding,
        )
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


class FinishedGoodAddition(models.Model):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='additions',
    )
    finished_good = models.ForeignKey(
        FinishedGood,
        on_delete=models.PROTECT,
        related_name='additions',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of finished goods received. Must be greater than zero.',
    )
    added_at = models.DateTimeField(
        default=timezone.now,
        help_text='When these finished goods entered inventory.',
    )
    production_output = models.ForeignKey(
        ProductionOutput,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_additions',
        help_text='Optional production output this addition came from.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Finished Good Addition'
        verbose_name_plural = 'Finished Good Additions'
        ordering = ('-added_at', 'warehouse', 'finished_good')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='fg_addition_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.warehouse.code} — {self.finished_good.code} — {self.quantity}"
        )

    def clean(self):
        super().clean()
        _validate_warehouse_finished_good(
            self.warehouse if self.warehouse_id else None,
            self.finished_good if self.finished_good_id else None,
            adding=self._state.adding,
        )
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })
        if self.production_output_id and self.warehouse_id:
            if self.production_output.production_run.factory_id != self.warehouse.factory_id:
                raise ValidationError({
                    'production_output': 'Production output must belong to the same factory as the warehouse.',
                })
        if (
            self.production_output_id
            and self.finished_good_id
            and self.production_output.finished_good_id
            and self.production_output.finished_good_id != self.finished_good_id
        ):
            raise ValidationError({
                'production_output': 'Production output must refer to the same finished good.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FinishedGoodAdjustmentType(models.TextChoices):
    INCREASE = 'INCREASE', 'Increase'
    DECREASE = 'DECREASE', 'Decrease'


class FinishedGoodAdjustment(models.Model):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='adjustments',
    )
    finished_good = models.ForeignKey(
        FinishedGood,
        on_delete=models.PROTECT,
        related_name='adjustments',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Absolute quantity to increase or decrease. Must be greater than zero.',
    )
    adjustment_type = models.CharField(
        max_length=20,
        choices=FinishedGoodAdjustmentType.choices,
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        help_text='When this adjustment occurred.',
    )
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Finished Good Adjustment'
        verbose_name_plural = 'Finished Good Adjustments'
        ordering = ('-occurred_at', 'warehouse', 'finished_good')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='fg_adjustment_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        sign = '+' if self.adjustment_type == FinishedGoodAdjustmentType.INCREASE else '-'
        return (
            f"{self.warehouse.code} — {self.finished_good.code} — "
            f"{sign}{self.quantity}"
        )

    def clean(self):
        super().clean()
        if self.reason:
            self.reason = self.reason.strip()
        _validate_warehouse_finished_good(
            self.warehouse if self.warehouse_id else None,
            self.finished_good if self.finished_good_id else None,
            adding=self._state.adding,
        )
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FinishedGoodDispatch(models.Model):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='dispatches',
    )
    finished_good = models.ForeignKey(
        FinishedGood,
        on_delete=models.PROTECT,
        related_name='dispatches',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantity of finished goods that left inventory. Must be greater than zero.',
    )
    dispatched_at = models.DateTimeField(
        default=timezone.now,
        help_text='When these finished goods left warehouse inventory.',
    )
    reference = models.CharField(
        max_length=50,
        blank=True,
        help_text='Optional operational reference. This is not a sales order or invoice.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Finished Good Dispatch'
        verbose_name_plural = 'Finished Good Dispatches'
        ordering = ('-dispatched_at', 'warehouse', 'finished_good')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='fg_dispatch_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.warehouse.code} — {self.finished_good.code} — {self.quantity}"
        )

    def clean(self):
        super().clean()
        if self.reference:
            self.reference = self.reference.strip()
        _validate_warehouse_finished_good(
            self.warehouse if self.warehouse_id else None,
            self.finished_good if self.finished_good_id else None,
            adding=self._state.adding,
        )
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FinishedGoodReconciliation(models.Model):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='reconciliations',
    )
    finished_good = models.ForeignKey(
        FinishedGood,
        on_delete=models.PROTECT,
        related_name='reconciliations',
    )
    reconciliation_date = models.DateField()
    notes = models.TextField(blank=True)
    expected_closing_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text='Opening + additions + adjustment increases − adjustment decreases − dispatches.',
    )
    actual_closing_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        help_text='Copied from the matching finished-good stock record closing quantity.',
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
        verbose_name = 'Finished Good Reconciliation'
        verbose_name_plural = 'Finished Good Reconciliations'
        ordering = ('-reconciliation_date', 'warehouse', 'finished_good')
        constraints = [
            models.UniqueConstraint(
                fields=['warehouse', 'finished_good', 'reconciliation_date'],
                name='unique_fg_reconciliation_per_warehouse_item_date',
            ),
        ]

    def __str__(self):
        return (
            f"{self.warehouse.code} — {self.finished_good.code} — "
            f"{self.reconciliation_date}"
        )

    def clean(self):
        super().clean()
        _validate_warehouse_finished_good(
            self.warehouse if self.warehouse_id else None,
            self.finished_good if self.finished_good_id else None,
            adding=self._state.adding,
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def calculate(self):
        from apps.production.services import reconcile_finished_goods

        return reconcile_finished_goods(self)
