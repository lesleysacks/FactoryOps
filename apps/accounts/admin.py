"""
FactoryOps Accounts — Django Admin Registration
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Extends Django's built-in UserAdmin to expose FactoryOps-specific fields.
    """
    list_display = ('username', 'email', 'get_full_name', 'role', 'factory', 'is_active', 'is_staff')
    list_filter = ('role', 'factory', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'employee_id')
    ordering = ('username',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('FactoryOps', {
            'fields': ('role', 'employee_id', 'factory'),
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('FactoryOps', {
            'fields': ('role', 'employee_id', 'factory'),
        }),
    )
