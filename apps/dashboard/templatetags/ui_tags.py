from django import template

register = template.Library()

SUCCESS = {
    'COMPLETED', 'FULFILLED', 'ALLOCATED', 'OPERATIONAL',
}
WARNING = {
    'PLANNED', 'OPEN', 'UNFULFILLED', 'PARTIALLY_ALLOCATED',
    'PARTIALLY_FULFILLED', 'PENDING', 'PARTIAL', 'MAINTENANCE',
}
DANGER = {
    'CANCELLED', 'DECOMMISSIONED', 'OFFLINE',
}
INFO = {
    'IN_PROGRESS', 'RUNNING',
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
