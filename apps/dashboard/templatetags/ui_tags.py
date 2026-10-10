from django import template

register = template.Library()

SUCCESS = {
    'COMPLETED', 'FULFILLED', 'ALLOCATED', 'OPERATIONAL',
    'QC_COMPLETE', 'INPUTS_COMPLETE', 'OK', 'VERIFIED',
}
WARNING = {
    'PLANNED', 'OPEN', 'UNFULFILLED', 'PARTIALLY_ALLOCATED',
    'PARTIALLY_FULFILLED', 'PENDING', 'PARTIAL', 'MAINTENANCE',
    'DRAFT', 'QC_REQUIRED', 'VALIDATION', 'WITHIN_TOLERANCE',
}
DANGER = {
    'CANCELLED', 'DECOMMISSIONED', 'OFFLINE', 'EXCEPTION',
}
INFO = {
    'IN_PROGRESS', 'RUNNING', 'PRODUCTION_ACTIVE', 'OUTPUT_RECORDED',
}


@register.simple_tag
def status_tone(value):
    if value is None:
        return 'neutral'
    key = str(value).upper().replace(' ', '_')
    if key in SUCCESS:
        return 'success'
    if key in WARNING or 'PARTIAL' in key:
        return 'warning'
    if key in DANGER:
        return 'danger'
    if key in INFO or 'PROGRESS' in key:
        return 'info'
    return 'neutral'


@register.filter
def variance_tone(value):
    try:
        if value is None:
            return 'neutral'
        if value == 0:
            return 'success'
        return 'danger'
    except (TypeError, ValueError):
        return 'neutral'
