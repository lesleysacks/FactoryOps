"""
FactoryOps Machines — Django Admin Registration
"""

from django.contrib import admin

from apps.accounts.access import configuration_admin_allowed
from apps.accounts.admin_access import RoleBoundAdminMixin

from .models import Machine


@admin.register(Machine)
class MachineAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'production_line__factory_id'
    list_display = ('code', 'name', 'production_line', 'is_active', 'created_at')
    list_filter = (
        ('production_line__factory', admin.RelatedOnlyFieldListFilter),
        ('production_line', admin.RelatedOnlyFieldListFilter),
        'is_active',
    )
    search_fields = ('name', 'code', 'production_line__name')
    readonly_fields = ('created_at',)
