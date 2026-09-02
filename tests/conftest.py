"""Test bootstrap.

Sets dummy environment variables *before* the app modules are imported so that
`config.py`'s fail-fast validation passes without real credentials, and adds the
project root to sys.path. No test in this suite makes a network call.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet-id")
os.environ.setdefault(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    '{"type": "service_account", "project_id": "test"}',
)
os.environ.setdefault("ALLOWED_TELEGRAM_USER_ID", "123456")
os.environ.setdefault("APP_TIMEZONE", "Africa/Cairo")
