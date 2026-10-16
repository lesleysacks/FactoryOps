"""Google Sheets API adapter.

The sync service talks to a small gateway. Tests pass a fake gateway and never
construct this client. ``build()`` is the only place that contacts Google, and
only after an explicit sync.
"""

import socket

from apps.reports.errors import SheetsCallError
from apps.reports.formatting import format_requests, sheet_range

SCOPES = ('https://www.googleapis.com/auth/spreadsheets',)


def load_service_account(path):
    """Load a service-account file. Failures stay generic so the key is not echoed."""
    try:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    except Exception:
        raise SheetsCallError(
            'config',
            'Could not load the Google service account file.',
        ) from None


def classify_transport_failure(exc):
    """Map a library or network error onto a safe SheetsCallError."""
    if isinstance(exc, SheetsCallError):
        return exc
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return SheetsCallError('timeout', 'The Google Sheets request timed out.')
    name = type(exc).__name__
    module = type(exc).__module__ or ''
    if name == 'HttpError' and module.startswith('googleapiclient'):
        status = int(getattr(exc.resp, 'status', 0) or 0)
        retry_after = _retry_after(getattr(exc, 'resp', None))
        return _from_status(status, retry_after)
    text = str(exc).lower()
    if 'timed out' in text or 'timeout' in text:
        return SheetsCallError('timeout', 'The Google Sheets request timed out.')
    return SheetsCallError('transient', 'The Google Sheets request failed.')


def _from_status(status, retry_after):
    if status == 429:
        return SheetsCallError('rate_limit', 'Google Sheets rate limit reached.', retry_after)
    if status in (408, 504):
        return SheetsCallError('timeout', f'Google Sheets HTTP {status}.', retry_after)
    if status in (500, 502, 503):
        return SheetsCallError('transient', f'Google Sheets HTTP {status}.', retry_after)
    if status in (401, 403):
        return SheetsCallError('permanent', f'Google Sheets HTTP {status}. The caller was not allowed.')
    return SheetsCallError('permanent', f'Google Sheets HTTP {status}.')


def _retry_after(resp):
    if resp is None:
        return None
    raw = None
    if hasattr(resp, 'get'):
        raw = resp.get('retry-after')
    if raw in (None, '') and hasattr(resp, '__getitem__'):
        try:
            raw = resp['retry-after']
        except Exception:
            raw = None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def build_service(credentials_file, timeout):
    credentials = load_service_account(credentials_file)
    try:
        import httplib2
        import google_auth_httplib2
        from googleapiclient.discovery import build
        authed = google_auth_httplib2.AuthorizedHttp(
            credentials,
            http=httplib2.Http(timeout=timeout),
        )
        return build('sheets', 'v4', http=authed, cache_discovery=False)
    except Exception:
        raise SheetsCallError('config', 'Could not start the Google Sheets client.') from None


class GoogleSheetsApi:
    """Thin wrapper around spreadsheets().values and batchUpdate."""

    def __init__(self, spreadsheet_id, service):
        self.spreadsheet_id = spreadsheet_id
        self.service = service

    def _call(self, request):
        try:
            return request.execute()
        except Exception as exc:
            raise classify_transport_failure(exc) from None

    def spreadsheet_sheets(self):
        body = self._call(self.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            fields='sheets.properties(title,sheetId)',
        ))
        sheets = []
        for sheet in body.get('sheets', []):
            props = sheet.get('properties', {})
            sheets.append({'title': props.get('title', ''), 'sheetId': props.get('sheetId')})
        return sheets

    def add_sheet(self, title):
        body = self._call(self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={'requests': [{'addSheet': {'properties': {'title': title}}}]},
        ))
        return body['replies'][0]['addSheet']['properties']['sheetId']

    def read_values(self, range_name):
        body = self._call(self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
        ))
        return body.get('values', [])

    def write_values(self, range_name, rows):
        self._call(self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',
            body={'values': rows},
        ))

    def format_sheet(self, requests):
        if not requests:
            return
        self._call(self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={'requests': requests},
        ))

    def update_rows(self, data):
        if not data:
            return
        self._call(self.service.spreadsheets().values().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={'valueInputOption': 'USER_ENTERED', 'data': data},
        ))

    def append_rows(self, range_name, rows):
        body = self._call(self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': rows},
        ))
        updates = body.get('updates') or {}
        return updates.get('updatedRange', '')


class GoogleSheetsGateway:
    """Prepare a tab, then update or append rows keyed by column A."""

    def __init__(self, spreadsheet_id, credentials_file, timeout, api=None):
        self.spreadsheet_id = spreadsheet_id
        self.credentials_file = credentials_file
        self.timeout = timeout
        self._api = api

    @property
    def api(self):
        if self._api is None:
            self._api = GoogleSheetsApi(
                self.spreadsheet_id,
                build_service(self.credentials_file, self.timeout),
            )
        return self._api

    def prepare(self, title, columns):
        sheets = {item['title']: item['sheetId'] for item in self.api.spreadsheet_sheets()}
        if title in sheets:
            sheet_id = sheets[title]
        else:
            sheet_id = self.api.add_sheet(title)
        existing = _first_row(self.api.read_values(sheet_range(title, '1:1')))
        expected = [column.header for column in columns]
        if existing and existing != expected:
            raise SheetsCallError(
                'permanent',
                'Worksheet header does not match FactoryOps. Restore the header row or use a new tab.',
            )
        if not existing:
            self.api.write_values(sheet_range(title, 'A1'), [expected])
        self.api.format_sheet(format_requests(sheet_id, columns))

    def source_key_rows(self, title):
        values = self.api.read_values(sheet_range(title, 'A2:A'))
        found = {}
        for offset, row in enumerate(values):
            if not row or row[0] in (None, ''):
                continue
            key = str(row[0]).strip()
            if key and key not in found:
                found[key] = offset + 2
        return found

    def write_rows(self, title, updates):
        data = []
        for row_number, cells in updates:
            data.append({
                'range': sheet_range(title, f'A{row_number}'),
                'values': [list(cells)],
            })
        self.api.update_rows(data)

    def append_rows(self, title, rows):
        if not rows:
            return []
        updated = self.api.append_rows(sheet_range(title, 'A1'), [list(row) for row in rows])
        start = _start_row(updated)
        if start is None:
            return []
        return list(range(start, start + len(rows)))


def build_google_gateway():
    from django.conf import settings
    return GoogleSheetsGateway(
        spreadsheet_id=settings.GOOGLE_SHEETS_SPREADSHEET_ID,
        credentials_file=settings.GOOGLE_SHEETS_CREDENTIALS_FILE,
        timeout=settings.GOOGLE_SHEETS_TIMEOUT_SECONDS,
    )


def _first_row(values):
    if not values or not values[0]:
        return []
    return ['' if cell is None else str(cell) for cell in values[0]]


def _start_row(updated_range):
    if not updated_range or '!' not in updated_range:
        return None
    cells = updated_range.split('!', 1)[1]
    start = cells.split(':', 1)[0]
    digits = ''.join(character for character in start if character.isdigit())
    if not digits:
        return None
    return int(digits)
