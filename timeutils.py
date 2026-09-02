"""Timezone-aware datetime helpers.

All date/time values in the app (record dates, `Created At` stamps, the anchor
for resolving relative dates like "today") must go through these helpers so the
behaviour is consistent regardless of where the server runs. The zone is
`config.TZ` (default Africa/Cairo, override with APP_TIMEZONE).
"""

from datetime import datetime

import config

DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def now() -> datetime:
    """Current time in the configured timezone."""
    return datetime.now(config.TZ)


def today_str() -> str:
    """Current date (YYYY-MM-DD) in the configured timezone."""
    return now().strftime(DATE_FMT)


def timestamp_str() -> str:
    """Current timestamp (YYYY-MM-DD HH:MM:SS) in the configured timezone."""
    return now().strftime(DATETIME_FMT)


def from_unix(ts: int) -> datetime:
    """Convert a Unix timestamp (UTC seconds, e.g. Telegram's message `date`)
    into a datetime in the configured timezone."""
    return datetime.fromtimestamp(ts, config.TZ)
