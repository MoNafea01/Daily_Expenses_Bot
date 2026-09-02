import os
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON_RAW = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
ALLOWED_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID")

# Optional: shared secret used to authenticate Telegram webhook calls and the
# /setup-webhook endpoint. When set, it is registered with Telegram via
# setWebhook(secret_token=...) and every incoming webhook must echo it back in
# the "X-Telegram-Bot-Api-Secret-Token" header. Leaving it unset keeps the
# previous (unauthenticated) behaviour for backward compatibility.
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET") or None

# Timezone used to resolve "today"/"yesterday" and to stamp records. Defaults to
# Africa/Cairo (the bot's user base); override with APP_TIMEZONE.
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Africa/Cairo")

# Validate required configuration
missing = []
if not TELEGRAM_BOT_TOKEN:
    missing.append("TELEGRAM_BOT_TOKEN")
if not GROQ_API_KEY:
    missing.append("GROQ_API_KEY")
if not GOOGLE_SHEET_ID:
    missing.append("GOOGLE_SHEET_ID")
if not GOOGLE_SERVICE_ACCOUNT_JSON_RAW:
    missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")
if not ALLOWED_USER_ID:
    missing.append("ALLOWED_TELEGRAM_USER_ID")

if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# Load service account credentials from JSON string
try:
    GOOGLE_SERVICE_ACCOUNT_JSON = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON_RAW)
except json.JSONDecodeError as e:
    raise ValueError(
        "Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON as JSON. "
        f"Please ensure it is a valid JSON string. Error: {e}"
    )

# Resolve the timezone once at startup, falling back to UTC if the name is
# unknown or the tz database is unavailable.
try:
    TZ = ZoneInfo(APP_TIMEZONE)
except (ZoneInfoNotFoundError, ModuleNotFoundError, ValueError):
    TZ = ZoneInfo("UTC")
