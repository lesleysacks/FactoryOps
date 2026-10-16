from django.contrib import admin

from apps.accounts.access import configuration_admin_allowed
from apps.accounts.admin_access import RoleBoundAdminMixin

from .models import SheetSyncRecord, SheetSyncRun


@admin.register(SheetSyncRecord)
class SheetSyncRecordAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    """Read-only delivery state. Payload is omitted so copied rows stay out of the page."""

    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    writes_allowed = False
    list_display = (
        'source_key',
        'status',
        'attempt_count',
        'sheet_row',
        'synced_at',
        'updated_at',
    )
    list_filter = ('dataset', 'status')
    search_fields = ('source_key', 'source_model')
    readonly_fields = (
        'dataset',
        'source_model',
        'source_id',
        'source_key',
        'factory',
        'payload_hash',
        'status',
        'attempt_count',
        'next_attempt_at',
        'last_error',
        'sheet_row',
        'synced_at',
        'created_at',
        'updated_at',
    )
    fields = readonly_fields


@admin.register(SheetSyncRun)
class SheetSyncRunAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = ''
    writes_allowed = False
    list_display = ('started_at', 'outcome', 'trigger', 'synced_count', 'failed_count', 'pending_count')
    readonly_fields = (
        'started_at',
        'finished_at',
        'trigger',
        'actor',
        'outcome',
        'message',
        'synced_count',
        'failed_count',
        'pending_count',
    )
    fields = readonly_fields
