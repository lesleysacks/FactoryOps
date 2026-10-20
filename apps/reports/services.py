"""
Read-only production and QC reports.

Output totals come from ProductionOutput rows. QC comparison calls
apps.production.variance and does not save operator or QC quantities.

Factory scope is stricter than the dashboard helper: a user with no factory
sees rows only when they are a platform admin. Everyone else with no factory
sees an empty report.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Sum

from apps.accounts.access import _platform_admin
from apps.production.models import ProductionOutput, ProductionRun
from apps.production.variance import recorded_quantity_for_run, variance_for_run
from apps.reports.windows import window_for_day, window_for_week_ending


ZERO = Decimal('0.000')
QUANTITY_QUANTUM = Decimal('0.001')


def _as_quantity(value):
    if value is None:
        return ZERO
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def _stored_verification(run):
    try:
        return run.qc_verification
    except ProductionRun.qc_verification.RelatedObjectDoesNotExist:
        return None


def scoped_production_outputs(user):
    """ProductionOutput rows this user is allowed to summarise."""
    queryset = ProductionOutput.objects.select_related(
        'production_run',
        'production_run__factory',
    )
    if _platform_admin(user):
        return queryset
    factory_id = getattr(user, 'factory_id', None)
    if not factory_id:
        return queryset.none()
    return queryset.filter(production_run__factory_id=factory_id)


def _outputs_in_window(user, window):
    return scoped_production_outputs(user).filter(
        recorded_at__date__gte=window.start,
        recorded_at__date__lte=window.end,
    )


def production_summary(user, window):
    """
    Daily rows for every UTC date in ``window``, plus the window total.

    The total quantity is the sum of those daily rows. A run is counted on
    each day it has output; ``run_count`` on the window is distinct runs.
    """
    queryset = _outputs_in_window(user, window)
    grouped = queryset.values('recorded_at__date').annotate(
        output_quantity=Sum('quantity'),
        output_count=Count('pk'),
        run_count=Count('production_run', distinct=True),
    )
    by_date = {row['recorded_at__date']: row for row in grouped}
    days = []
    day = window.start
    while day <= window.end:
        row = by_date.get(day)
        if row is None:
            days.append({
                'date': day,
                'output_quantity': ZERO,
                'output_count': 0,
                'run_count': 0,
            })
        else:
            days.append({
                'date': day,
                'output_quantity': _as_quantity(row['output_quantity']),
                'output_count': row['output_count'],
                'run_count': row['run_count'],
            })
        day += timedelta(days=1)
    return {
        'timezone_label': window.timezone_label,
        'start': window.start,
        'end': window.end,
        'day_count': window.day_count,
        'output_quantity': _as_quantity(
            sum((item['output_quantity'] for item in days), ZERO)
        ),
        'output_count': queryset.count(),
        'run_count': queryset.values('production_run_id').distinct().count(),
        'days': days,
    }


def daily_production_summary(user, day):
    return production_summary(user, window_for_day(day))


def weekly_production_summary(user, week_ending):
    """Totals for the rolling seven UTC days ending on ``week_ending``."""
    return production_summary(user, window_for_week_ending(week_ending))


def qc_variance_report(user, window):
    """
    One read-only variance row per run that recorded output in the window.

    The date filter selects runs. Figures come from variance_for_run, which
    uses the full run (frozen recorded quantity when QC stored one). This
    report does not write ProductionOutput or QCVerification.
    """
    run_ids = list(
        _outputs_in_window(user, window)
        .values_list('production_run_id', flat=True)
        .distinct()
    )
    runs = (
        ProductionRun.objects.filter(pk__in=run_ids)
        .select_related('factory')
        .order_by('reference', 'pk')
    )
    rows = []
    for run in runs:
        verification = _stored_verification(run)
        result = variance_for_run(run)
        rows.append({
            'run_id': run.pk,
            'reference': run.reference,
            'factory_name': run.factory.name,
            'operator_output_quantity': recorded_quantity_for_run(run),
            'recorded_quantity': result['recorded'],
            'expected_quantity': result['expected'],
            'qc_verified_quantity': result['qc_verified'],
            'qc_vs_recorded': result['qc_vs_recorded'],
            'recorded_vs_expected': result['recorded_vs_expected'],
            'variance_status': result['status'],
            'tolerance_pct': result['tolerance_pct'],
            'qc_record_status': (
                verification.status if verification is not None else None
            ),
        })
    return {
        'timezone_label': window.timezone_label,
        'start': window.start,
        'end': window.end,
        'rows': rows,
    }
