"""
FactoryOps Factories — Django Admin Registration
"""

from django.contrib import admin

from .models import Factory, ProductionLine


class ProductionLineInline(admin.TabularInline):
    model = ProductionLine
    extra = 0
    fields = ('name', 'description', 'is_active')


@admin.register(Factory)
class FactoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'location')
    inlines = [ProductionLineInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProductionLine)
class ProductionLineAdmin(admin.ModelAdmin):
    list_display = ('name', 'factory', 'is_active', 'created_at')
    list_filter = ('factory', 'is_active')
    search_fields = ('name', 'factory__name')
    readonly_fields = ('created_at',)
