import os
import json
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON_RAW = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
ALLOWED_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID")

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
    raise ValueError(f"Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON as JSON. Please ensure it is a valid JSON string. Error: {e}")
