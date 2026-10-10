"""
FactoryOps Materials — Django Admin Registration
"""

from django.contrib import admin

from .models import (
    Material,
    MaterialAddition,
    MaterialBatch,
    MaterialCategory,
    MaterialConsumption,
    MaterialScrap,
    MaterialWaste,
    StockReconciliation,
    StockRecord,
    UnitOfMeasure,
)


class UserFactoryAdminMixin:
    """Default new material records to the logged-in user's factory."""

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if getattr(request.user, 'factory_id', None):
            initial.setdefault('factory', request.user.factory_id)
        return initial

    def save_model(self, request, obj, form, change):
        if not change and getattr(request.user, 'factory_id', None):
            obj.factory_id = request.user.factory_id
        super().save_model(request, obj, form, change)


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('name', 'symbol', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'symbol')
    readonly_fields = ('created_at',)


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(UserFactoryAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'factory', 'is_active', 'created_at')
    list_filter = ('factory', 'is_active')
    search_fields = ('name', 'factory__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Material)
class MaterialAdmin(UserFactoryAdminMixin, admin.ModelAdmin):
    list_display = (
        'code',
        'name',
        'factory',
        'category',
        'unit',
        'minimum_stock_threshold',
        'target_stock',
        'is_active',
    )
    list_filter = ('factory', 'category', 'unit', 'is_active')
    search_fields = ('name', 'code', 'factory__name', 'category__name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('factory', 'code', 'name', 'category', 'unit', 'is_active'),
        }),
        ('Stock Thresholds', {
            'fields': ('minimum_stock_threshold', 'target_stock'),
        }),
        ('Notes', {
            'fields': ('notes',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
        }),
    )


@admin.register(StockRecord)
class StockRecordAdmin(admin.ModelAdmin):
    list_display = (
        'recording_date',
        'factory',
        'material',
        'opening_quantity',
        'closing_quantity',
    )
    list_filter = ('factory', 'material', 'recording_date')
    search_fields = ('material__code', 'material__name', 'factory__name')
    list_select_related = ('factory', 'material')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'recording_date'
    fieldsets = (
        (None, {
            'fields': ('factory', 'material', 'recording_date'),
        }),
        ('Quantities', {
            'fields': ('opening_quantity', 'closing_quantity'),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
        }),
    )


@admin.register(MaterialBatch)
class MaterialBatchAdmin(admin.ModelAdmin):
    list_display = ('lot_number', 'material', 'created_at')
    list_filter = ('material__factory', 'material')
    search_fields = ('lot_number', 'material__code', 'material__name')
    list_select_related = ('material', 'material__factory')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MaterialAddition)
class MaterialAdditionAdmin(admin.ModelAdmin):
    list_display = (
        'added_at',
        'factory',
        'material',
        'batch',
        'quantity',
    )
    list_filter = ('factory', 'material', 'added_at')
    search_fields = (
        'material__code',
        'material__name',
        'batch__lot_number',
        'factory__name',
    )
    list_select_related = ('factory', 'material', 'batch')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'added_at'
    fieldsets = (
        (None, {
            'fields': ('factory', 'material', 'batch', 'added_at'),
        }),
        ('Quantity', {
            'fields': ('quantity',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
        }),
    )


@admin.register(MaterialConsumption)
class MaterialConsumptionAdmin(admin.ModelAdmin):
    list_display = (
        'consumed_at',
        'factory',
        'material',
        'batch',
        'quantity',
        'production_run',
        'recorded_by',
        'production_reference',
    )
    list_filter = ('factory', 'material', 'production_run', 'consumed_at')
    search_fields = (
        'material__code',
        'material__name',
        'batch__lot_number',
        'production_reference',
        'production_run__reference',
        'factory__name',
    )
    list_select_related = ('factory', 'material', 'batch', 'production_run', 'recorded_by')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'consumed_at'
    fieldsets = (
        (None, {
            'fields': (
                'factory',
                'material',
                'batch',
                'consumed_at',
                'production_run',
                'production_reference',
                'recorded_by',
            ),
        }),
        ('Quantity', {
            'fields': ('quantity',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
        }),
    )


@admin.register(MaterialWaste)
class MaterialWasteAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at',
        'factory',
        'material',
        'quantity',
        'reason',
    )
    list_filter = ('factory', 'material', 'occurred_at')
    search_fields = (
        'material__code',
        'material__name',
        'reason',
        'factory__name',
    )
    list_select_related = ('factory', 'material')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'occurred_at'


@admin.register(MaterialScrap)
class MaterialScrapAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at',
        'factory',
        'material',
        'quantity',
        'reason',
    )
    list_filter = ('factory', 'material', 'occurred_at')
    search_fields = (
        'material__code',
        'material__name',
        'reason',
        'factory__name',
    )
    list_select_related = ('factory', 'material')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'occurred_at'


@admin.register(StockReconciliation)
class StockReconciliationAdmin(admin.ModelAdmin):
    list_display = (
        'reconciliation_date',
        'factory',
        'material',
        'expected_closing_quantity',
        'actual_closing_quantity',
        'variance_quantity',
    )
    list_filter = ('factory', 'material', 'reconciliation_date')
    search_fields = ('material__code', 'material__name', 'factory__name', 'notes')
    list_select_related = ('factory', 'material')
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
            'fields': ('factory', 'material', 'reconciliation_date', 'notes'),
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
