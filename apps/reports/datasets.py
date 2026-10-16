"""Approved reporting datasets.

Each dataset reads existing FactoryOps rows. Downtime and shift handovers are
listed so management can see why they are absent. Those apps have no models,
and this integration does not invent any.

Personal fields are not mapped: user names, email addresses, employee numbers,
free-text notes, and QC photo files. A future dataset can be added here without
a Google Forms or Apps Script dependency.
"""

from dataclasses import dataclass

from django.db.models import Count

from apps.materials.models import (
    MaterialAddition,
    MaterialConsumption,
    MaterialScrap,
    MaterialWaste,
)
from apps.production.models import (
    FinishedGoodAddition,
    FinishedGoodAdjustment,
    FinishedGoodDispatch,
    ProductionOutput,
    QCVerification,
)
from apps.reports.formatting import (
    Column,
    datetime_cell,
    decimal_cell,
    integer_cell,
    text_cell,
)


@dataclass(frozen=True)
class ReportRow:
    source_model: str
    source_id: int
    source_key: str
    factory_id: int | None
    cells: tuple


@dataclass(frozen=True)
class Dataset:
    key: str
    title: str
    available: bool
    unavailable_reason: str
    columns: tuple
    collect: object


def _key(dataset, source_model, source_id):
    return f'{dataset}:{source_model}:{source_id}'


def _line(run):
    line = run.production_line
    if line is None:
        return ''
    if line.code:
        return f'{line.name} ({line.code})'
    return line.name


PRODUCTION_OUTPUT_COLUMNS = (
    Column('Source key', 'text'),
    Column('Source ID', 'number', '0'),
    Column('Factory', 'text'),
    Column('Run reference', 'text'),
    Column('Run status', 'text'),
    Column('Run stage', 'text'),
    Column('Production line', 'text'),
    Column('Machine', 'text'),
    Column('Product code', 'text'),
    Column('Variant code', 'text'),
    Column('Packaging code', 'text'),
    Column('Output name', 'text'),
    Column('Finished good', 'text'),
    Column('Quantity', 'number', '0.000'),
    Column('Recorded at (UTC)', 'datetime', 'yyyy-mm-dd hh:mm:ss'),
    Column('Updated at (UTC)', 'datetime', 'yyyy-mm-dd hh:mm:ss'),
)

QC_RESULT_COLUMNS = (
    Column('Source key', 'text'),
    Column('Source ID', 'number', '0'),
    Column('Factory', 'text'),
    Column('Run reference', 'text'),
    Column('Status', 'text'),
    Column('Variant code', 'text'),
    Column('Packaging code', 'text'),
    Column('Expected quantity', 'number', '0.000'),
    Column('Recorded quantity', 'number', '0.000'),
    Column('QC verified quantity', 'number', '0.000'),
    Column('Verified at (UTC)', 'datetime', 'yyyy-mm-dd hh:mm:ss'),
    Column('Photo count', 'number', '0'),
    Column('Updated at (UTC)', 'datetime', 'yyyy-mm-dd hh:mm:ss'),
)

STOCK_MOVEMENT_COLUMNS = (
    Column('Source key', 'text'),
    Column('Source ID', 'number', '0'),
    Column('Movement type', 'text'),
    Column('Factory', 'text'),
    Column('Occurred at (UTC)', 'datetime', 'yyyy-mm-dd hh:mm:ss'),
    Column('Item code', 'text'),
    Column('Item name', 'text'),
    Column('Quantity', 'number', '0.000'),
    Column('Unit', 'text'),
    Column('Batch lot', 'text'),
    Column('Warehouse', 'text'),
    Column('Run reference', 'text'),
    Column('Adjustment type', 'text'),
    Column('Reason or reference', 'text'),
    Column('Updated at (UTC)', 'datetime', 'yyyy-mm-dd hh:mm:ss'),
)


def collect_production_output(factory_id=None):
    queryset = ProductionOutput.objects.select_related(
        'production_run__factory',
        'production_run__production_line',
        'production_run__machine',
        'production_run__product',
        'production_run__variant',
        'production_run__packaging',
        'finished_good',
    ).order_by('pk')
    if factory_id is not None:
        queryset = queryset.filter(production_run__factory_id=factory_id)
    rows = []
    source_model = 'production.ProductionOutput'
    for output in queryset:
        run = output.production_run
        finished = output.finished_good.code if output.finished_good_id else ''
        source_key = _key('production_output', source_model, output.pk)
        rows.append(ReportRow(
            source_model=source_model,
            source_id=output.pk,
            source_key=source_key,
            factory_id=run.factory_id,
            cells=(
                text_cell(source_key),
                integer_cell(output.pk),
                text_cell(run.factory.name),
                text_cell(run.reference),
                text_cell(run.get_status_display()),
                text_cell(run.get_stage_display() if run.stage else ''),
                text_cell(_line(run)),
                text_cell(run.machine.code if run.machine_id else ''),
                text_cell(run.product.code if run.product_id else ''),
                text_cell(run.variant.code if run.variant_id else ''),
                text_cell(run.packaging.code if run.packaging_id else ''),
                text_cell(output.output_name),
                text_cell(finished),
                decimal_cell(output.quantity),
                datetime_cell(output.recorded_at),
                datetime_cell(output.updated_at),
            ),
        ))
    return rows


def collect_qc_results(factory_id=None):
    queryset = QCVerification.objects.select_related(
        'production_run__factory',
        'variant',
        'packaging',
    ).annotate(photo_count=Count('photos')).order_by('pk')
    if factory_id is not None:
        queryset = queryset.filter(production_run__factory_id=factory_id)
    rows = []
    source_model = 'production.QCVerification'
    for verification in queryset:
        run = verification.production_run
        source_key = _key('qc_results', source_model, verification.pk)
        rows.append(ReportRow(
            source_model=source_model,
            source_id=verification.pk,
            source_key=source_key,
            factory_id=run.factory_id,
            cells=(
                text_cell(source_key),
                integer_cell(verification.pk),
                text_cell(run.factory.name),
                text_cell(run.reference),
                text_cell(verification.get_status_display()),
                text_cell(verification.variant.code if verification.variant_id else ''),
                text_cell(verification.packaging.code if verification.packaging_id else ''),
                decimal_cell(verification.expected_quantity),
                decimal_cell(verification.recorded_quantity),
                decimal_cell(verification.qc_verified_quantity),
                datetime_cell(verification.verified_at),
                integer_cell(verification.photo_count),
                datetime_cell(verification.updated_at),
            ),
        ))
    return rows


def _stock_cells(
    *,
    movement_type,
    source_model,
    source_id,
    factory_id,
    factory_name,
    occurred_at,
    item_code,
    item_name,
    quantity,
    unit='',
    batch_lot='',
    warehouse='',
    run_reference='',
    adjustment_type='',
    reason='',
    updated_at,
):
    source_key = _key('stock_movements', source_model, source_id)
    return ReportRow(
        source_model=source_model,
        source_id=source_id,
        source_key=source_key,
        factory_id=factory_id,
        cells=(
            text_cell(source_key),
            integer_cell(source_id),
            text_cell(movement_type),
            text_cell(factory_name),
            datetime_cell(occurred_at),
            text_cell(item_code),
            text_cell(item_name),
            decimal_cell(quantity),
            text_cell(unit),
            text_cell(batch_lot),
            text_cell(warehouse),
            text_cell(run_reference),
            text_cell(adjustment_type),
            text_cell(reason),
            datetime_cell(updated_at),
        ),
    )


def collect_stock_movements(factory_id=None):
    rows = []
    additions = MaterialAddition.objects.select_related(
        'factory', 'material__unit', 'batch',
    ).order_by('pk')
    consumptions = MaterialConsumption.objects.select_related(
        'factory', 'material__unit', 'batch', 'production_run',
    ).order_by('pk')
    waste = MaterialWaste.objects.select_related('factory', 'material__unit').order_by('pk')
    scrap = MaterialScrap.objects.select_related('factory', 'material__unit').order_by('pk')
    fg_additions = FinishedGoodAddition.objects.select_related(
        'warehouse__factory', 'finished_good', 'production_output__production_run',
    ).order_by('pk')
    adjustments = FinishedGoodAdjustment.objects.select_related(
        'warehouse__factory', 'finished_good',
    ).order_by('pk')
    dispatches = FinishedGoodDispatch.objects.select_related(
        'warehouse__factory', 'finished_good',
    ).order_by('pk')
    if factory_id is not None:
        additions = additions.filter(factory_id=factory_id)
        consumptions = consumptions.filter(factory_id=factory_id)
        waste = waste.filter(factory_id=factory_id)
        scrap = scrap.filter(factory_id=factory_id)
        fg_additions = fg_additions.filter(warehouse__factory_id=factory_id)
        adjustments = adjustments.filter(warehouse__factory_id=factory_id)
        dispatches = dispatches.filter(warehouse__factory_id=factory_id)

    for item in additions:
        rows.append(_stock_cells(
            movement_type='material_addition',
            source_model='materials.MaterialAddition',
            source_id=item.pk,
            factory_id=item.factory_id,
            factory_name=item.factory.name,
            occurred_at=item.added_at,
            item_code=item.material.code,
            item_name=item.material.name,
            quantity=item.quantity,
            unit=item.material.unit.symbol,
            batch_lot=item.batch.lot_number,
            updated_at=item.updated_at,
        ))
    for item in consumptions:
        run_reference = ''
        if item.production_run_id:
            run_reference = item.production_run.reference
        elif item.production_reference:
            run_reference = item.production_reference
        rows.append(_stock_cells(
            movement_type='material_consumption',
            source_model='materials.MaterialConsumption',
            source_id=item.pk,
            factory_id=item.factory_id,
            factory_name=item.factory.name,
            occurred_at=item.consumed_at,
            item_code=item.material.code,
            item_name=item.material.name,
            quantity=item.quantity,
            unit=item.material.unit.symbol,
            batch_lot=item.batch.lot_number if item.batch_id else '',
            run_reference=run_reference,
            updated_at=item.updated_at,
        ))
    for item in waste:
        rows.append(_stock_cells(
            movement_type='material_waste',
            source_model='materials.MaterialWaste',
            source_id=item.pk,
            factory_id=item.factory_id,
            factory_name=item.factory.name,
            occurred_at=item.occurred_at,
            item_code=item.material.code,
            item_name=item.material.name,
            quantity=item.quantity,
            unit=item.material.unit.symbol,
            reason=item.reason,
            updated_at=item.updated_at,
        ))
    for item in scrap:
        rows.append(_stock_cells(
            movement_type='material_scrap',
            source_model='materials.MaterialScrap',
            source_id=item.pk,
            factory_id=item.factory_id,
            factory_name=item.factory.name,
            occurred_at=item.occurred_at,
            item_code=item.material.code,
            item_name=item.material.name,
            quantity=item.quantity,
            unit=item.material.unit.symbol,
            reason=item.reason,
            updated_at=item.updated_at,
        ))
    for item in fg_additions:
        run_reference = ''
        if item.production_output_id:
            run_reference = item.production_output.production_run.reference
        rows.append(_stock_cells(
            movement_type='finished_good_addition',
            source_model='production.FinishedGoodAddition',
            source_id=item.pk,
            factory_id=item.warehouse.factory_id,
            factory_name=item.warehouse.factory.name,
            occurred_at=item.added_at,
            item_code=item.finished_good.code,
            item_name=item.finished_good.name,
            quantity=item.quantity,
            warehouse=item.warehouse.code,
            run_reference=run_reference,
            updated_at=item.updated_at,
        ))
    for item in adjustments:
        rows.append(_stock_cells(
            movement_type='finished_good_adjustment',
            source_model='production.FinishedGoodAdjustment',
            source_id=item.pk,
            factory_id=item.warehouse.factory_id,
            factory_name=item.warehouse.factory.name,
            occurred_at=item.occurred_at,
            item_code=item.finished_good.code,
            item_name=item.finished_good.name,
            quantity=item.quantity,
            warehouse=item.warehouse.code,
            adjustment_type=item.get_adjustment_type_display(),
            reason=item.reason,
            updated_at=item.updated_at,
        ))
    for item in dispatches:
        rows.append(_stock_cells(
            movement_type='finished_good_dispatch',
            source_model='production.FinishedGoodDispatch',
            source_id=item.pk,
            factory_id=item.warehouse.factory_id,
            factory_name=item.warehouse.factory.name,
            occurred_at=item.dispatched_at,
            item_code=item.finished_good.code,
            item_name=item.finished_good.name,
            quantity=item.quantity,
            warehouse=item.warehouse.code,
            reason=item.reference,
            updated_at=item.updated_at,
        ))
    return rows


DATASETS = (
    Dataset(
        key='production_output',
        title='Production output',
        available=True,
        unavailable_reason='',
        columns=PRODUCTION_OUTPUT_COLUMNS,
        collect=collect_production_output,
    ),
    Dataset(
        key='qc_results',
        title='QC results',
        available=True,
        unavailable_reason='',
        columns=QC_RESULT_COLUMNS,
        collect=collect_qc_results,
    ),
    Dataset(
        key='stock_movements',
        title='Stock movements',
        available=True,
        unavailable_reason='',
        columns=STOCK_MOVEMENT_COLUMNS,
        collect=collect_stock_movements,
    ),
    Dataset(
        key='downtime',
        title='Downtime',
        available=False,
        unavailable_reason='No downtime records exist yet. apps.downtime has no source model.',
        columns=(),
        collect=None,
    ),
    Dataset(
        key='shift_handovers',
        title='Shift handovers',
        available=False,
        unavailable_reason='No shift handover records exist yet. apps.handovers has no source model.',
        columns=(),
        collect=None,
    ),
)

_BY_KEY = {dataset.key: dataset for dataset in DATASETS}


def all_datasets():
    return DATASETS


def dataset_by_key(key):
    return _BY_KEY.get(key)
