import re
from datetime import datetime, timezone

import timeutils


def test_today_str_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", timeutils.today_str())


def test_timestamp_str_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", timeutils.timestamp_str())


def test_from_unix_is_timezone_aware():
    dt = timeutils.from_unix(1_756_700_000)
    assert dt.tzinfo is not None


def test_from_unix_matches_utc_instant():
    ts = 1_756_700_000
    assert timeutils.from_unix(ts).timestamp() == datetime.fromtimestamp(
        ts, timezone.utc
    ).timestamp()


def test_now_uses_configured_zone():
    import config
    assert timeutils.now().tzinfo is config.TZ
