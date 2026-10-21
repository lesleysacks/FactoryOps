from django.contrib import admin

from apps.accounts.access import configuration_admin_allowed
from apps.accounts.admin_access import RoleBoundAdminMixin

from .models import Packaging, Product, ProductVariant


@admin.register(Product)
class ProductAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = ('code', 'name', 'factory', 'is_active', 'created_at')
    list_filter = (('factory', admin.RelatedOnlyFieldListFilter), 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProductVariant)
class ProductVariantAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'product__factory_id'
    list_display = ('code', 'name', 'product', 'finished_good', 'is_active', 'created_at')
    list_filter = (
        ('product__factory', admin.RelatedOnlyFieldListFilter),
        'is_active',
    )
    search_fields = ('code', 'name', 'product__code', 'product__name')
    list_select_related = ('product', 'product__factory', 'finished_good')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Packaging)
class PackagingAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = (
        'code',
        'name',
        'factory',
        'contains',
        'quantity_per',
        'base_unit_quantity',
        'is_active',
    )
    list_filter = (('factory', admin.RelatedOnlyFieldListFilter), 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory', 'contains')
    readonly_fields = ('created_at', 'updated_at')
