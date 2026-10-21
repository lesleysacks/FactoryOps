"""
FactoryOps Orders — Django Admin Registration
"""

from django.contrib import admin

from apps.accounts.access import configuration_admin_allowed
from apps.accounts.admin_access import RoleBoundAdminMixin

from .models import (
    Customer,
    CustomerOrder,
    CustomerOrderLine,
    DispatchAllocation,
    OrderReservation,
)


@admin.register(Customer)
class CustomerAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = (
        'code',
        'name',
        'factory',
        'contact_name',
        'email',
        'is_active',
        'created_at',
    )
    list_filter = (('factory', admin.RelatedOnlyFieldListFilter), 'is_active')
    search_fields = ('code', 'name', 'contact_name', 'email', 'factory__name')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CustomerOrder)
class CustomerOrderAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = (
        'reference',
        'factory',
        'customer',
        'order_date',
        'status',
        'fulfilment_status',
    )
    list_filter = (
        ('factory', admin.RelatedOnlyFieldListFilter),
        ('customer', admin.RelatedOnlyFieldListFilter),
        'status',
        'fulfilment_status',
        'order_date',
    )
    search_fields = (
        'reference',
        'customer__code',
        'customer__name',
        'factory__name',
        'notes',
    )
    list_select_related = ('factory', 'customer')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'order_date'


@admin.register(CustomerOrderLine)
class CustomerOrderLineAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'customer_order__factory_id'
    list_display = (
        'customer_order',
        'finished_good',
        'quantity',
    )
    list_filter = (
        ('customer_order__factory', admin.RelatedOnlyFieldListFilter),
        ('customer_order__customer', admin.RelatedOnlyFieldListFilter),
        'customer_order__status',
        ('finished_good', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'customer_order__reference',
        'customer_order__customer__code',
        'customer_order__customer__name',
        'finished_good__code',
        'finished_good__name',
    )
    list_select_related = (
        'customer_order',
        'customer_order__customer',
        'finished_good',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DispatchAllocation)
class DispatchAllocationAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'order_line__customer_order__factory_id'
    list_display = (
        'order_line',
        'dispatch',
        'quantity',
        'created_at',
    )
    list_filter = (
        ('order_line__customer_order__factory', admin.RelatedOnlyFieldListFilter),
        ('order_line__customer_order__customer', admin.RelatedOnlyFieldListFilter),
        'order_line__customer_order__status',
        ('order_line__finished_good', admin.RelatedOnlyFieldListFilter),
        ('dispatch__warehouse', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        'order_line__customer_order__reference',
        'order_line__customer_order__customer__code',
        'order_line__customer_order__customer__name',
        'order_line__finished_good__code',
        'dispatch__warehouse__code',
        'dispatch__reference',
    )
    list_select_related = (
        'order_line',
        'order_line__customer_order',
        'order_line__finished_good',
        'dispatch',
        'dispatch__warehouse',
        'dispatch__finished_good',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(OrderReservation)
class OrderReservationAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'order_line__customer_order__factory_id'
    list_display = (
        'order_line',
        'warehouse',
        'quantity',
        'created_at',
    )
    list_filter = (
        ('warehouse', admin.RelatedOnlyFieldListFilter),
        ('order_line__finished_good', admin.RelatedOnlyFieldListFilter),
        ('order_line__customer_order__customer', admin.RelatedOnlyFieldListFilter),
        ('order_line__customer_order__factory', admin.RelatedOnlyFieldListFilter),
        'order_line__customer_order__fulfilment_status',
    )
    search_fields = (
        'order_line__customer_order__reference',
        'order_line__customer_order__customer__code',
        'order_line__customer_order__customer__name',
        'order_line__finished_good__code',
        'warehouse__code',
        'warehouse__name',
    )
    list_select_related = (
        'warehouse',
        'order_line',
        'order_line__customer_order',
        'order_line__finished_good',
    )
    readonly_fields = ('created_at', 'updated_at')
