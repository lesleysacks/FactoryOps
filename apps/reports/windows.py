"""
UTC calendar date windows for FactoryOps reports.

TIME_ZONE is UTC. These boundaries are UTC dates. A factory-local timezone
is not applied in this slice.
"""

from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone


MAX_WINDOW_DAYS = 93
WEEK_LENGTH_DAYS = 7
TIMEZONE_LABEL = 'UTC'
_DATE_FORMAT = '%Y-%m-%d'


class DateWindow:
    """Inclusive UTC calendar dates. ``end`` is part of the window."""

    timezone_label = TIMEZONE_LABEL

    def __init__(self, start, end):
        self.start = start
        self.end = end

    @property
    def day_count(self):
        return (self.end - self.start).days + 1

    def __eq__(self, other):
        if not isinstance(other, DateWindow):
            return NotImplemented
        return self.start == other.start and self.end == other.end


def utc_today():
    return timezone.now().date()


def _as_date(value, field_name):
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValidationError(f'{field_name} must be a calendar date.')
    return value


def validate_window(start, end):
    """Accept an inclusive range of at most 93 UTC calendar days."""
    start = _as_date(start, 'Start date')
    end = _as_date(end, 'End date')
    if end < start:
        raise ValidationError('End date must be on or after the start date.')
    day_count = (end - start).days + 1
    if day_count > MAX_WINDOW_DAYS:
        raise ValidationError(
            f'Date range is {day_count} UTC calendar days. '
            f'Reports cover at most {MAX_WINDOW_DAYS} calendar days.'
        )
    return DateWindow(start, end)


def window_for_day(day):
    day = _as_date(day, 'Date')
    return DateWindow(day, day)


def window_for_week_ending(end):
    """Seven inclusive UTC calendar days, ending on ``end``."""
    end = _as_date(end, 'End date')
    start = end - timedelta(days=WEEK_LENGTH_DAYS - 1)
    return validate_window(start, end)


def parse_iso_date(value):
    """Parse ``YYYY-MM-DD``. Blank means the caller did not supply a date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, _DATE_FORMAT).date()
    except ValueError as exc:
        raise ValidationError('Use dates in YYYY-MM-DD format.') from exc
    return parsed


def resolve_window(start, end, *, today=None, preset='day'):
    """
    Resolve a report window.

    An explicit start and end are used together. One side on its own is
    rejected. With neither date, ``week`` is the seven UTC days ending today
    and any other preset is today.
    """
    if today is None:
        today = utc_today()
    today = _as_date(today, 'Today')
    parsed_start = parse_iso_date(start)
    parsed_end = parse_iso_date(end)
    if (parsed_start is None) != (parsed_end is None):
        raise ValidationError('Provide both a start date and an end date.')
    if parsed_start is not None:
        return validate_window(parsed_start, parsed_end)
    if preset == 'week':
        return window_for_week_ending(today)
    return window_for_day(today)
