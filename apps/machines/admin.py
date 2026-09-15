"""
FactoryOps Machines — Django Admin Registration
"""

from django.contrib import admin

from .models import Machine


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'production_line', 'is_active', 'created_at')
    list_filter = ('production_line__factory', 'production_line', 'is_active')
    search_fields = ('name', 'code', 'production_line__name')
    readonly_fields = ('created_at',)
