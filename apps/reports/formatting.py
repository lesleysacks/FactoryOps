"""Cell values and Google Sheets layout for management report tabs.

Column order is part of the published sheet contract. Adding a column belongs
at the end. Reordering an existing tab's header is refused at sync time so
older rows are not shifted under the wrong names.
"""

from datetime import timezone as dt_timezone
from decimal import Decimal

from django.utils import timezone


def text_cell(value):
    """Operational text. A leading formula character is forced to plain text."""
    if value is None:
        return ''
    text = str(value).replace('\r', ' ').replace('\n', ' ').strip()
    if text[:1] in ('=', '+', '-', '@', '\t'):
        return "'" + text
    return text


def decimal_cell(value):
    if value is None or value == '':
        return ''
    quantized = Decimal(value).quantize(Decimal('0.001'))
    return format(quantized, 'f')


def integer_cell(value):
    if value is None or value == '':
        return ''
    return str(int(value))


def datetime_cell(value):
    """UTC wall time that Sheets can parse when value input is USER_ENTERED."""
    if value is None:
        return ''
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    return value.astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


class Column:
    def __init__(self, header, kind, pattern=''):
        self.header = header
        self.kind = kind
        self.pattern = pattern

    def __eq__(self, other):
        return (
            isinstance(other, Column)
            and self.header == other.header
            and self.kind == other.kind
            and self.pattern == other.pattern
        )

    def __repr__(self):
        return f'Column({self.header!r}, {self.kind!r}, {self.pattern!r})'


def format_requests(sheet_id, columns):
    """Layout requests for one worksheet. Safe to send again on every sync."""
    width = len(columns)
    requests = [
        {
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'gridProperties': {'frozenRowCount': 1},
                },
                'fields': 'gridProperties.frozenRowCount',
            }
        },
        {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': width,
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 0.122, 'green': 0.306, 'blue': 0.475},
                        'textFormat': {
                            'bold': True,
                            'foregroundColor': {'red': 1, 'green': 1, 'blue': 1},
                        },
                    }
                },
                'fields': 'userEnteredFormat(backgroundColor,textFormat)',
            }
        },
    ]
    for index, column in enumerate(columns):
        if not column.pattern:
            continue
        number_type = 'DATE_TIME' if column.kind == 'datetime' else 'NUMBER'
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 1,
                    'startColumnIndex': index,
                    'endColumnIndex': index + 1,
                },
                'cell': {
                    'userEnteredFormat': {
                        'numberFormat': {'type': number_type, 'pattern': column.pattern},
                    }
                },
                'fields': 'userEnteredFormat.numberFormat',
            }
        })
    if width:
        requests.append({
            'setBasicFilter': {
                'filter': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0,
                        'startColumnIndex': 0,
                        'endColumnIndex': width,
                    }
                }
            }
        })
    return requests


def sheet_range(title, a1):
    safe = title.replace("'", "''")
    return f"'{safe}'!{a1}"
