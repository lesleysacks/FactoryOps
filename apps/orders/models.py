"""
FactoryOps Orders — Customer, Order, and Dispatch Allocation Models
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class CustomerOrderStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    PARTIALLY_ALLOCATED = 'PARTIALLY_ALLOCATED', 'Partially allocated'
    ALLOCATED = 'ALLOCATED', 'Allocated'
    CANCELLED = 'CANCELLED', 'Cancelled'


class CustomerOrderFulfilmentStatus(models.TextChoices):
    UNFULFILLED = 'UNFULFILLED', 'Unfulfilled'
    PARTIALLY_FULFILLED = 'PARTIALLY_FULFILLED', 'Partially fulfilled'
    FULFILLED = 'FULFILLED', 'Fulfilled'


class Customer(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='customers',
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    contact_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ('factory', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'code'],
                name='unique_customer_code_per_factory',
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
        if self.contact_name:
            self.contact_name = self.contact_name.strip()
        if self.phone:
            self.phone = self.phone.strip()
        if self._state.adding and self.factory_id and not self.factory.is_active:
            raise ValidationError({
                'factory': 'Cannot create a customer for an inactive factory.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CustomerOrder(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='customer_orders',
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='orders',
    )
    reference = models.CharField(max_length=50)
    order_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=CustomerOrderStatus.choices,
        default=CustomerOrderStatus.OPEN,
    )
    fulfilment_status = models.CharField(
        max_length=30,
        choices=CustomerOrderFulfilmentStatus.choices,
        default=CustomerOrderFulfilmentStatus.UNFULFILLED,
        help_text='Derived from dispatch allocations. Does not replace commercial status.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer Order'
        verbose_name_plural = 'Customer Orders'
        ordering = ('-order_date', 'factory', 'reference')
        constraints = [
            models.UniqueConstraint(
                fields=['factory', 'reference'],
                name='unique_customer_order_reference_per_factory',
            ),
        ]

    def __str__(self):
        return f"{self.factory.name} — {self.reference}"

    def clean(self):
        super().clean()
        if self.reference:
            self.reference = self.reference.strip()
        if self.factory_id and self.customer_id:
            if self.customer.factory_id != self.factory_id:
                raise ValidationError({
                    'customer': 'Customer must belong to the same factory as the order.',
                })
        if self._state.adding:
            if self.factory_id and not self.factory.is_active:
                raise ValidationError({
                    'factory': 'Cannot create an order for an inactive factory.',
                })
            if self.customer_id and not self.customer.is_active:
                raise ValidationError({
                    'customer': 'Cannot create an order for an inactive customer.',
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def calculate_fulfilment(self):
        from apps.orders.services import update_order_fulfilment

        return update_order_fulfilment(self)


class CustomerOrderLine(models.Model):
    customer_order = models.ForeignKey(
        CustomerOrder,
        on_delete=models.PROTECT,
        related_name='lines',
    )
    finished_good = models.ForeignKey(
        'production.FinishedGood',
        on_delete=models.PROTECT,
        related_name='order_lines',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Ordered quantity. Must be greater than zero.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer Order Line'
        verbose_name_plural = 'Customer Order Lines'
        ordering = ('customer_order', 'id')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='customer_order_line_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.customer_order.reference} — {self.finished_good.code} — "
            f"{self.quantity}"
        )

    def clean(self):
        super().clean()
        if self.customer_order_id and self.finished_good_id:
            if self.finished_good.factory_id != self.customer_order.factory_id:
                raise ValidationError({
                    'finished_good': (
                        'Finished good must belong to the same factory as the order.'
                    ),
                })
        if (
            self._state.adding
            and self.finished_good_id
            and not self.finished_good.is_active
        ):
            raise ValidationError({
                'finished_good': 'Cannot add an inactive finished good to an order.',
            })
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DispatchAllocation(models.Model):
    dispatch = models.ForeignKey(
        'production.FinishedGoodDispatch',
        on_delete=models.PROTECT,
        related_name='allocations',
    )
    order_line = models.ForeignKey(
        CustomerOrderLine,
        on_delete=models.PROTECT,
        related_name='allocations',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Allocated quantity. Must be greater than zero.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dispatch Allocation'
        verbose_name_plural = 'Dispatch Allocations'
        ordering = ('-created_at', 'order_line')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='dispatch_allocation_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.order_line.customer_order.reference} — "
            f"{self.dispatch.finished_good.code} — {self.quantity}"
        )

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })
        if not self.dispatch_id or not self.order_line_id:
            return
        order_factory_id = self.order_line.customer_order.factory_id
        dispatch_factory_id = self.dispatch.warehouse.factory_id
        if dispatch_factory_id != order_factory_id:
            raise ValidationError({
                'dispatch': 'Dispatch must belong to the same factory as the order.',
            })
        if self.dispatch.finished_good.factory_id != order_factory_id:
            raise ValidationError({
                'dispatch': 'Dispatch finished good must belong to the same factory as the order.',
            })
        if self.dispatch.finished_good_id != self.order_line.finished_good_id:
            raise ValidationError({
                'dispatch': 'Dispatch must refer to the same finished good as the order line.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class OrderReservation(models.Model):
    warehouse = models.ForeignKey(
        'production.Warehouse',
        on_delete=models.PROTECT,
        related_name='reservations',
    )
    order_line = models.ForeignKey(
        CustomerOrderLine,
        on_delete=models.PROTECT,
        related_name='reservations',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Committed quantity. Must be greater than zero. Does not reduce inventory.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Order Reservation'
        verbose_name_plural = 'Order Reservations'
        ordering = ('-created_at', 'order_line')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='order_reservation_quantity_greater_than_zero',
            ),
        ]

    def __str__(self):
        return (
            f"{self.order_line.customer_order.reference} — "
            f"{self.warehouse.code} — {self.quantity}"
        )

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError({
                'quantity': 'Quantity must be greater than zero.',
            })
        if not self.warehouse_id or not self.order_line_id:
            return
        order = self.order_line.customer_order
        finished_good = self.order_line.finished_good
        if self.warehouse.factory_id != order.factory_id:
            raise ValidationError({
                'warehouse': 'Warehouse must belong to the same factory as the order.',
            })
        if finished_good.factory_id != self.warehouse.factory_id:
            raise ValidationError({
                'order_line': 'Finished good must belong to the same factory as the warehouse.',
            })
        if self._state.adding and not self.warehouse.is_active:
            raise ValidationError({
                'warehouse': 'Cannot reserve stock against an inactive warehouse.',
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
