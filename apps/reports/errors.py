"""Errors raised while copying reports to an external destination."""


class SheetsCallError(Exception):
    """A Sheets call failed. ``message`` is safe to store and to log."""

    def __init__(self, kind, message, retry_after=None):
        self.kind = kind
        self.retry_after = retry_after
        super().__init__(message)
