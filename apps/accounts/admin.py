"""
FactoryOps Accounts — Django Admin Registration
"""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

from apps.accounts.access import configuration_admin_allowed, machines_limited_to_assignment

from .admin_access import RoleBoundAdminMixin
from .models import User


def _without_superuser(fields):
    cleaned = []
    for field in fields:
        if isinstance(field, (list, tuple)):
            nested = tuple(item for item in field if item != 'is_superuser')
            if nested:
                cleaned.append(nested)
        elif field != 'is_superuser':
            cleaned.append(field)
    return tuple(cleaned)


@admin.register(User)
class UserAdmin(RoleBoundAdminMixin, BaseUserAdmin):
    """
    Extends Django's built-in UserAdmin to expose FactoryOps-specific fields.

    Only an ADMIN (or a superuser) may open this screen. A plant admin cannot
    grant superuser or move an account to another factory.
    """
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = ('username', 'email', 'get_full_name', 'role', 'factory', 'is_active', 'is_staff')
    list_filter = (
        'role',
        ('factory', admin.RelatedOnlyFieldListFilter),
        'is_active',
        'is_staff',
    )
    filter_horizontal = BaseUserAdmin.filter_horizontal + ('assigned_machines',)
    search_fields = ('username', 'email', 'first_name', 'last_name', 'employee_id')
    ordering = ('username',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('FactoryOps', {
            'fields': ('role', 'employee_id', 'factory', 'assigned_machines'),
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('FactoryOps', {
            'fields': ('role', 'employee_id', 'factory', 'assigned_machines'),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        hidden = []
        for title, options in fieldsets:
            hidden.append((title, {**options, 'fields': _without_superuser(options.get('fields', ()))}))
        return hidden

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'assigned_machines' and getattr(request.user, 'factory_id', None):
            queryset = db_field.related_model.objects.filter(
                production_line__factory_id=request.user.factory_id,
            )
            if machines_limited_to_assignment(request.user):
                queryset = request.user.assigned_machines.all()
            kwargs['queryset'] = queryset
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            if change and obj.pk:
                previous = type(obj).objects.get(pk=obj.pk)
                if previous.is_superuser:
                    raise PermissionDenied(
                        'A superuser account can only be changed by a superuser.'
                    )
            obj.is_superuser = False
        super().save_model(request, obj, form, change)


admin.site.unregister(Group)


@admin.register(Group)
class ResponsibilityGroupAdmin(RoleBoundAdminMixin, GroupAdmin):
    """Responsibility groups are access control, so only an admin may edit them."""

    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = None
