"""
FactoryOps Production — Django Admin Registration
"""

from django.contrib import admin

from .models import (
    FinishedGood,
    FinishedGoodAddition,
    FinishedGoodAdjustment,
    FinishedGoodDispatch,
    FinishedGoodReconciliation,
    FinishedGoodStockRecord,
    ProductionOutput,
    ProductionReject,
    ProductionRun,
    ProductionRunMaterialState,
    Warehouse,
)


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = (
        'reference',
        'factory',
        'production_line',
        'machine',
        'status',
        'created_by',
        'started_at',
        'ended_at',
        'created_at',
    )
    list_filter = ('factory', 'status', 'production_line')
    search_fields = ('reference', 'factory__name', 'notes')
    list_select_related = ('factory', 'production_line', 'machine', 'created_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProductionOutput)
class ProductionOutputAdmin(admin.ModelAdmin):
    list_display = (
        'recorded_at',
        'production_run',
        'output_name',
        'finished_good',
        'quantity',
    )
    list_filter = ('production_run__factory', 'finished_good', 'recorded_at')
    search_fields = (
        'output_name',
        'production_run__reference',
        'finished_good__code',
        'finished_good__name',
    )
    list_select_related = ('production_run', 'finished_good')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'recorded_at'


@admin.register(ProductionRunMaterialState)
class ProductionRunMaterialStateAdmin(admin.ModelAdmin):
    list_display = (
        'recorded_at',
        'production_run',
        'material',
        'roll_quantity',
        'spare_roll_quantity',
        'recorded_by',
    )
    list_filter = ('production_run__factory', 'material', 'recorded_at')
    search_fields = (
        'production_run__reference',
        'material__code',
        'material__name',
    )
    list_select_related = ('production_run', 'material', 'recorded_by')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'recorded_at'


@admin.register(ProductionReject)
class ProductionRejectAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at',
        'production_run',
        'quantity',
        'reason',
    )
    list_filter = ('production_run__factory', 'occurred_at')
    search_fields = ('production_run__reference', 'reason')
    list_select_related = ('production_run',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'occurred_at'


@admin.register(FinishedGood)
class FinishedGoodAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'factory', 'is_active', 'created_at')
    list_filter = ('factory', 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'factory', 'is_active', 'created_at')
    list_filter = ('factory', 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FinishedGoodStockRecord)
class FinishedGoodStockRecordAdmin(admin.ModelAdmin):
    list_display = (
        'recording_date',
        'warehouse',
        'finished_good',
        'opening_quantity',
        'closing_quantity',
    )
    list_filter = ('warehouse', 'finished_good', 'recording_date')
    search_fields = (
        'warehouse__code',
        'warehouse__name',
        'finished_good__code',
        'finished_good__name',
    )
    list_select_related = ('warehouse', 'finished_good')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'recording_date'


@admin.register(FinishedGoodAddition)
class FinishedGoodAdditionAdmin(admin.ModelAdmin):
    list_display = (
        'added_at',
        'warehouse',
        'finished_good',
        'quantity',
        'production_output',
    )
    list_filter = ('warehouse', 'finished_good', 'added_at')
    search_fields = (
        'warehouse__code',
        'finished_good__code',
        'finished_good__name',
    )
    list_select_related = ('warehouse', 'finished_good', 'production_output')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'added_at'


@admin.register(FinishedGoodAdjustment)
class FinishedGoodAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at',
        'warehouse',
        'finished_good',
        'adjustment_type',
        'quantity',
        'reason',
    )
    list_filter = ('warehouse', 'finished_good', 'adjustment_type', 'occurred_at')
    search_fields = (
        'warehouse__code',
        'finished_good__code',
        'finished_good__name',
        'reason',
    )
    list_select_related = ('warehouse', 'finished_good')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'occurred_at'


@admin.register(FinishedGoodDispatch)
class FinishedGoodDispatchAdmin(admin.ModelAdmin):
    list_display = (
        'dispatched_at',
        'warehouse',
        'finished_good',
        'quantity',
        'reference',
    )
    list_filter = ('warehouse', 'finished_good', 'dispatched_at')
    search_fields = (
        'warehouse__code',
        'finished_good__code',
        'finished_good__name',
        'reference',
        'notes',
    )
    list_select_related = ('warehouse', 'finished_good')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'dispatched_at'


@admin.register(FinishedGoodReconciliation)
class FinishedGoodReconciliationAdmin(admin.ModelAdmin):
    list_display = (
        'reconciliation_date',
        'warehouse',
        'finished_good',
        'expected_closing_quantity',
        'actual_closing_quantity',
        'variance_quantity',
    )
    list_filter = ('warehouse', 'finished_good', 'reconciliation_date')
    search_fields = (
        'warehouse__code',
        'finished_good__code',
        'finished_good__name',
        'notes',
    )
    list_select_related = ('warehouse', 'finished_good')
    readonly_fields = (
        'expected_closing_quantity',
        'actual_closing_quantity',
        'variance_quantity',
        'calculated_at',
        'created_at',
        'updated_at',
    )
    date_hierarchy = 'reconciliation_date'
    actions = ('calculate_reconciliations',)
    fieldsets = (
        (None, {
            'fields': ('warehouse', 'finished_good', 'reconciliation_date', 'notes'),
        }),
        ('Results', {
            'fields': (
                'expected_closing_quantity',
                'actual_closing_quantity',
                'variance_quantity',
                'calculated_at',
            ),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.action(description='Calculate selected reconciliations')
    def calculate_reconciliations(self, request, queryset):
        for reconciliation in queryset:
            reconciliation.calculate()
