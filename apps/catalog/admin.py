from django.contrib import admin

from .models import Packaging, Product, ProductVariant


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'factory', 'is_active', 'created_at')
    list_filter = ('factory', 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'product', 'finished_good', 'is_active', 'created_at')
    list_filter = ('product__factory', 'is_active')
    search_fields = ('code', 'name', 'product__code', 'product__name')
    list_select_related = ('product', 'product__factory', 'finished_good')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Packaging)
class PackagingAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'name',
        'factory',
        'contains',
        'quantity_per',
        'base_unit_quantity',
        'is_active',
    )
    list_filter = ('factory', 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory', 'contains')
    readonly_fields = ('created_at', 'updated_at')
