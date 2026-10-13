from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'factory',
        'actor',
        'action',
        'field_name',
        'old_value',
        'new_value',
    )
    list_filter = ('factory', 'action', 'created_at')
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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
