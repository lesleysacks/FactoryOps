"""UTC date windows for reports. Boundaries are calendar days, not local plant time."""

from datetime import date, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.reports.windows import (
    MAX_WINDOW_DAYS,
    resolve_window,
    validate_window,
    window_for_day,
    window_for_week_ending,
)


TODAY = date(2026, 10, 20)


def test_single_day_window_is_inclusive():
    window = window_for_day(TODAY)
    assert window.start == TODAY
    assert window.end == TODAY
    assert window.day_count == 1
    assert window.timezone_label == 'UTC'


def test_week_is_seven_inclusive_utc_days_ending_on_the_given_date():
    window = window_for_week_ending(TODAY)
    assert window.end == TODAY
    assert window.start == date(2026, 10, 14)
    assert window.day_count == 7


def test_missing_dates_default_to_the_utc_day():
    window = resolve_window(None, '', today=TODAY, preset='day')
    assert window.start == TODAY
    assert window.end == TODAY


def test_week_preset_uses_the_supplied_today():
    window = resolve_window(None, None, today=TODAY, preset='week')
    assert window == window_for_week_ending(TODAY)


def test_explicit_dates_ignore_the_week_preset():
    window = resolve_window(
        '2026-02-01',
        '2026-02-03',
        today=TODAY,
        preset='week',
    )
    assert window.start == date(2026, 2, 1)
    assert window.end == date(2026, 2, 3)
    assert window.day_count == 3


def test_same_start_and_end_is_one_day():
    window = validate_window(TODAY, TODAY)
    assert window.day_count == 1


def test_ninety_three_inclusive_days_is_allowed():
    start = date(2026, 1, 1)
    end = start + timedelta(days=MAX_WINDOW_DAYS - 1)
    window = validate_window(start, end)
    assert window.day_count == MAX_WINDOW_DAYS


def test_ninety_four_inclusive_days_is_rejected():
    start = date(2026, 1, 1)
    end = start + timedelta(days=MAX_WINDOW_DAYS)
    with pytest.raises(ValidationError) as caught:
        validate_window(start, end)
    assert '93' in ' '.join(caught.value.messages)


def test_end_before_start_is_rejected():
    with pytest.raises(ValidationError):
        validate_window(TODAY, TODAY - timedelta(days=1))


def test_one_side_of_the_range_is_rejected():
    with pytest.raises(ValidationError):
        resolve_window('2026-10-01', None, today=TODAY)
    with pytest.raises(ValidationError):
        resolve_window('  ', '2026-10-20', today=TODAY)


@pytest.mark.parametrize('value', ['2026-13-01', '20-10-2026', '2026/10/20', 'yesterday'])
def test_unparseable_dates_are_rejected(value):
    with pytest.raises(ValidationError):
        resolve_window(value, '2026-10-20', today=TODAY)


def test_datetimes_are_not_accepted_as_calendar_dates():
    stamp = datetime(2026, 10, 20, 0, 0)
    with pytest.raises(ValidationError):
        validate_window(stamp, TODAY)
