from django.contrib import admin

from apps.accounts.access import audit_admin_allowed
from apps.accounts.admin_access import RoleBoundAdminMixin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(audit_admin_allowed)
    factory_lookup = 'factory_id'
    writes_allowed = False
    list_display = (
        'created_at',
        'factory',
        'actor',
        'action',
        'field_name',
        'old_value',
        'new_value',
    )
    list_filter = (
        ('factory', admin.RelatedOnlyFieldListFilter),
        'action',
        'created_at',
    )
    search_fields = ('field_name', 'old_value', 'new_value', 'reason', 'actor__username')
    list_select_related = ('factory', 'actor', 'target_content_type')
    readonly_fields = (
        'factory',
        'actor',
        'action',
        'target_content_type',
        'target_object_id',
        'field_name',
        'old_value',
        'new_value',
        'reason',
        'created_at',
    )
