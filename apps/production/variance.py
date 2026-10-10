"""
FactoryOps Production — deterministic variance between expected, recorded, and QC.

Auto-correct means compute the expected value and name the discrepancy.
It never overwrites the operator's recorded quantity.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Sum

from apps.catalog.services import individual_units
from apps.production.models import FactoryProductionPolicy

ZERO = Decimal('0')
QUANTITY_QUANTUM = Decimal('0.001')
FACTORY_DEFAULT = Decimal('0.000')
DEFAULT_MIN_QC_PHOTOS = 1

VARIANCE_OK = 'OK'
VARIANCE_WITHIN_TOLERANCE = 'WITHIN_TOLERANCE'
VARIANCE_EXCEPTION = 'EXCEPTION'
VARIANCE_INSUFFICIENT = 'INSUFFICIENT_DATA'


def _as_quantity(value):
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def policy_for_factory(factory):
    if factory is None:
        return None
    return FactoryProductionPolicy.objects.filter(factory=factory).first()


def tolerance_pct_for(factory):
    policy = policy_for_factory(factory)
    if policy is None or policy.tolerance_pct is None:
        return FACTORY_DEFAULT
    return _as_quantity(policy.tolerance_pct)


def min_qc_photos_for(factory):
    policy = policy_for_factory(factory)
    if policy is None or not policy.min_qc_photos:
        return DEFAULT_MIN_QC_PHOTOS
    return policy.min_qc_photos


def expected_individual_units(run):
    """Planned packs × individual units in the selected packaging. None if incomplete."""
    if run is None or not run.packaging_id or run.planned_pack_quantity is None:
        return None
    return _as_quantity(run.planned_pack_quantity * individual_units(run.packaging))


def recorded_quantity_for_run(run):
    if run is None or not run.pk:
        return None
    total = run.outputs.aggregate(total=Sum('quantity'))['total']
    if total is None:
        return None
    return _as_quantity(total)


def _delta(left, right):
    if left is None or right is None:
        return None
    return _as_quantity(left - right)


def _percent(delta, expected):
    if delta is None or expected is None or expected <= 0:
        return None
    return _as_quantity((delta / expected) * Decimal('100'))


def compute_variance(
    expected,
    recorded,
    qc_verified,
    *,
    tolerance_pct=FACTORY_DEFAULT,
):
    """Pure comparison. Missing inputs yield INSUFFICIENT_DATA and no writes."""
    expected = _as_quantity(expected)
    recorded = _as_quantity(recorded)
    qc_verified = _as_quantity(qc_verified)
    for value in (expected, recorded, qc_verified):
        if value is not None and value < 0:
            raise ValidationError('Quantities cannot be negative.')
    tolerance = _as_quantity(tolerance_pct if tolerance_pct is not None else FACTORY_DEFAULT)
    if tolerance is None or tolerance < 0:
        tolerance = FACTORY_DEFAULT

    recorded_vs_expected = _delta(recorded, expected)
    qc_vs_expected = _delta(qc_verified, expected)
    qc_vs_recorded = _delta(qc_verified, recorded)
    recorded_vs_expected_pct = _percent(recorded_vs_expected, expected)
    qc_vs_expected_pct = _percent(qc_vs_expected, expected)

    if expected is None or recorded is None or qc_verified is None:
        status = VARIANCE_INSUFFICIENT
    else:
        status = _variance_status(
            expected,
            recorded,
            qc_verified,
            recorded_vs_expected_pct,
            qc_vs_expected_pct,
            tolerance,
        )

    return {
        'expected': expected,
        'recorded': recorded,
        'qc_verified': qc_verified,
        'recorded_vs_expected': recorded_vs_expected,
        'qc_vs_expected': qc_vs_expected,
        'qc_vs_recorded': qc_vs_recorded,
        'recorded_vs_expected_pct': recorded_vs_expected_pct,
        'qc_vs_expected_pct': qc_vs_expected_pct,
        'status': status,
        'tolerance_pct': tolerance,
    }


def _variance_status(expected, recorded, qc_verified, recorded_pct, qc_pct, tolerance):
    if expected <= 0:
        if recorded != expected or qc_verified != expected:
            return VARIANCE_EXCEPTION
        return VARIANCE_OK
    worst = max(abs(recorded_pct or ZERO), abs(qc_pct or ZERO))
    if worst == 0:
        return VARIANCE_OK
    if worst <= tolerance:
        return VARIANCE_WITHIN_TOLERANCE
    return VARIANCE_EXCEPTION


def variance_for_run(run, *, tolerance_pct=None):
    """Read stored QC quantities when present, otherwise derive what is known."""
    verification = getattr(run, 'qc_verification', None)
    if verification is None:
        try:
            verification = run.qc_verification
        except run.__class__.qc_verification.RelatedObjectDoesNotExist:
            verification = None

    if verification is not None and verification.expected_quantity is not None:
        expected = _as_quantity(verification.expected_quantity)
    else:
        expected = expected_individual_units(run)

    if verification is not None and verification.recorded_quantity is not None:
        recorded = _as_quantity(verification.recorded_quantity)
    else:
        recorded = recorded_quantity_for_run(run)

    qc_verified = None
    if verification is not None:
        qc_verified = _as_quantity(verification.qc_verified_quantity)

    if tolerance_pct is None:
        tolerance_pct = tolerance_pct_for(run.factory)
    return compute_variance(
        expected,
        recorded,
        qc_verified,
        tolerance_pct=tolerance_pct,
    )


def variance_to_json(result):
    """Decimal values as strings so callers can serialize without inventing maths."""
    payload = {}
    for key, value in result.items():
        if isinstance(value, Decimal):
            payload[key] = format(value, 'f')
        else:
            payload[key] = value
    return payload
