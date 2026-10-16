"""Remove credential material before it reaches logs, the database, or a page."""

import re


_PRIVATE_KEY = re.compile(
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
    re.DOTALL,
)
_JSON_SECRET = re.compile(
    r'("(?:private_key|private_key_id|client_secret|refresh_token)"\s*:\s*")([^"]*)(")',
    re.IGNORECASE,
)
_TOKEN = re.compile(
    r'(ya29\.[A-Za-z0-9_\-]+|Bearer\s+[A-Za-z0-9_\-\.]+)',
    re.IGNORECASE,
)


def redact(value, limit=500):
    """Return a short string with private keys and access tokens removed."""
    if value is None:
        return ''
    text = str(value)
    text = _PRIVATE_KEY.sub('[redacted]', text)
    text = _JSON_SECRET.sub(r'\1[redacted]\3', text)
    text = _TOKEN.sub('[redacted]', text)
    text = text.replace('\r', ' ').replace('\n', ' ')
    if len(text) > limit:
        return text[: max(limit - 1, 0)] + '…'
    return text
