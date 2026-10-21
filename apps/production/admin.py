"""
FactoryOps Production — Django Admin Registration
"""

from django.contrib import admin

from apps.accounts.access import (
    configuration_admin_allowed,
    enforce_production_admin_write,
    inventory_admin_allowed,
    production_admin_allowed,
    qc_admin_allowed,
    scope_production_admin,
)
from apps.accounts.admin_access import RoleBoundAdminMixin, limit_admin_foreign_keys

from .models import (
    FactoryProductionPolicy,
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
    QCPhoto,
    QCVerification,
    Warehouse,
)


class ProductionManagementAdmin(admin.ModelAdmin):
    """Production-run admin follows the same role and machine limits as the floor."""

    production_scope_prefix = ''

    def has_module_permission(self, request):
        return production_admin_allowed(request.user)

    def has_view_permission(self, request, obj=None):
        return production_admin_allowed(request.user)

    def has_add_permission(self, request):
        return production_admin_allowed(request.user)

    def has_change_permission(self, request, obj=None):
        return production_admin_allowed(request.user)

    def has_delete_permission(self, request, obj=None):
        return production_admin_allowed(request.user)

    def get_queryset(self, request):
        return scope_production_admin(
            super().get_queryset(request),
            request.user,
            self.production_scope_prefix,
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        limit_admin_foreign_keys(db_field, request, kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        enforce_production_admin_write(request.user, obj)
        super().save_model(request, obj, form, change)


@admin.register(ProductionRun)
class ProductionRunAdmin(ProductionManagementAdmin):
    list_display = (
        'reference',
        'factory',
        'production_line',
        'machine',
        'status',
        'stage',
        'product',
        'created_by',
        'started_at',
        'ended_at',
        'created_at',
    )
    list_filter = (
        ('factory', admin.RelatedOnlyFieldListFilter),
        'status',
        ('production_line', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ('reference', 'factory__name', 'notes')
    list_select_related = ('factory', 'production_line', 'machine', 'created_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProductionOutput)
class ProductionOutputAdmin(ProductionManagementAdmin):
    production_scope_prefix = 'production_run__'
    list_display = (
        'recorded_at',
        'production_run',
        'output_name',
        'finished_good',
        'quantity',
    )
    list_filter = (
        ('production_run__factory', admin.RelatedOnlyFieldListFilter),
        ('finished_good', admin.RelatedOnlyFieldListFilter),
        'recorded_at',
    )
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
class ProductionRunMaterialStateAdmin(ProductionManagementAdmin):
    production_scope_prefix = 'production_run__'
    list_display = (
        'recorded_at',
        'production_run',
        'material',
        'roll_quantity',
        'spare_roll_quantity',
        'recorded_by',
    )
    list_filter = (
        ('production_run__factory', admin.RelatedOnlyFieldListFilter),
        ('material', admin.RelatedOnlyFieldListFilter),
        'recorded_at',
    )
    search_fields = (
        'production_run__reference',
        'material__code',
        'material__name',
    )
    list_select_related = ('production_run', 'material', 'recorded_by')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'recorded_at'


@admin.register(ProductionReject)
class ProductionRejectAdmin(ProductionManagementAdmin):
    production_scope_prefix = 'production_run__'
    list_display = (
        'occurred_at',
        'production_run',
        'quantity',
        'reason',
    )
    list_filter = (
        ('production_run__factory', admin.RelatedOnlyFieldListFilter),
        'occurred_at',
    )
    search_fields = ('production_run__reference', 'reason')
    list_select_related = ('production_run',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'occurred_at'


@admin.register(FinishedGood)
class FinishedGoodAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = ('code', 'name', 'factory', 'is_active', 'created_at')
    list_filter = (('factory', admin.RelatedOnlyFieldListFilter), 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Warehouse)
class WarehouseAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = ('code', 'name', 'factory', 'is_active', 'created_at')
    list_filter = (('factory', admin.RelatedOnlyFieldListFilter), 'is_active')
    search_fields = ('code', 'name', 'factory__name')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FinishedGoodStockRecord)
class FinishedGoodStockRecordAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(inventory_admin_allowed)
    factory_lookup = 'warehouse__factory_id'
    list_display = (
        'recording_date',
        'warehouse',
        'finished_good',
        'opening_quantity',
        'closing_quantity',
    )
    list_filter = (
        ('warehouse', admin.RelatedOnlyFieldListFilter),
        ('finished_good', admin.RelatedOnlyFieldListFilter),
        'recording_date',
    )
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
class FinishedGoodAdditionAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(inventory_admin_allowed)
    factory_lookup = 'warehouse__factory_id'
    list_display = (
        'added_at',
        'warehouse',
        'finished_good',
        'quantity',
        'production_output',
    )
    list_filter = (
        ('warehouse', admin.RelatedOnlyFieldListFilter),
        ('finished_good', admin.RelatedOnlyFieldListFilter),
        'added_at',
    )
    search_fields = (
        'warehouse__code',
        'finished_good__code',
        'finished_good__name',
    )
    list_select_related = ('warehouse', 'finished_good', 'production_output')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'added_at'


@admin.register(FinishedGoodAdjustment)
class FinishedGoodAdjustmentAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(inventory_admin_allowed)
    factory_lookup = 'warehouse__factory_id'
    list_display = (
        'occurred_at',
        'warehouse',
        'finished_good',
        'adjustment_type',
        'quantity',
        'reason',
    )
    list_filter = (
        ('warehouse', admin.RelatedOnlyFieldListFilter),
        ('finished_good', admin.RelatedOnlyFieldListFilter),
        'adjustment_type',
        'occurred_at',
    )
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
class FinishedGoodDispatchAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(inventory_admin_allowed)
    factory_lookup = 'warehouse__factory_id'
    list_display = (
        'dispatched_at',
        'warehouse',
        'finished_good',
        'quantity',
        'reference',
    )
    list_filter = (
        ('warehouse', admin.RelatedOnlyFieldListFilter),
        ('finished_good', admin.RelatedOnlyFieldListFilter),
        'dispatched_at',
    )
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
class FinishedGoodReconciliationAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(inventory_admin_allowed)
    factory_lookup = 'warehouse__factory_id'
    list_display = (
        'reconciliation_date',
        'warehouse',
        'finished_good',
        'expected_closing_quantity',
        'actual_closing_quantity',
        'variance_quantity',
    )
    list_filter = (
        ('warehouse', admin.RelatedOnlyFieldListFilter),
        ('finished_good', admin.RelatedOnlyFieldListFilter),
        'reconciliation_date',
    )
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


@admin.register(FactoryProductionPolicy)
class FactoryProductionPolicyAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(configuration_admin_allowed)
    factory_lookup = 'factory_id'
    list_display = ('factory', 'tolerance_pct', 'min_qc_photos', 'updated_at')
    list_select_related = ('factory',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(QCVerification)
class QCVerificationAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(qc_admin_allowed)
    factory_lookup = 'production_run__factory_id'
    writes_allowed = False
    list_display = (
        'production_run',
        'status',
        'variant',
        'packaging',
        'expected_quantity',
        'recorded_quantity',
        'qc_verified_quantity',
        'verified_by',
    )
    list_filter = (
        'status',
        ('production_run__factory', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ('production_run__reference',)
    list_select_related = (
        'production_run',
        'variant',
        'packaging',
        'verified_by',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(QCPhoto)
class QCPhotoAdmin(RoleBoundAdminMixin, admin.ModelAdmin):
    access_check = staticmethod(qc_admin_allowed)
    factory_lookup = 'qc_verification__production_run__factory_id'
    writes_allowed = False
    list_display = ('uploaded_at', 'qc_verification', 'uploaded_by', 'caption')
    list_select_related = ('qc_verification', 'uploaded_by')
    readonly_fields = ('created_at', 'updated_at', 'uploaded_at')
