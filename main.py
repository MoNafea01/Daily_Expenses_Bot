import logging
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request, Query, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import agent
import telegram_utils
import config
import timeutils

# Configure logging to standard output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
allowed_user_id = config.ALLOWED_USER_ID

app = FastAPI(
    title="Daily Expenses Bot Server",
    description=(
        "FastAPI Webhook Server that parses expense records using LangGraph, "
        "DSPy, and Groq, then persists them in Google Sheets."
    ),
    version="1.0.0",
)

# Serve the financial dashboard frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.warning("Static directory not found: %s", STATIC_DIR)

# ------------------------------------------------------------------ #
#  Idempotency: skip Telegram updates we've already handled          #
# ------------------------------------------------------------------ #
# Telegram redelivers an update (same update_id) whenever it does not get a
# prompt 200 - which is easy to trigger while the LLM + Sheets round-trips run.
# Without a guard, each retry appends the expense again. This bounded in-memory
# set catches the common fast-retry storm on a warm instance. On a multi-instance
# or frequently cold-started deployment, back this with a shared KV store
# (e.g. Vercel KV / Upstash Redis) keyed by update_id.
_SEEN_UPDATE_IDS: "OrderedDict[int, None]" = OrderedDict()
_SEEN_MAX = 512
_seen_lock = Lock()


def _already_processed(update_id) -> bool:
    if update_id is None:
        return False
    with _seen_lock:
        if update_id in _SEEN_UPDATE_IDS:
            return True
        _SEEN_UPDATE_IDS[update_id] = None
        while len(_SEEN_UPDATE_IDS) > _SEEN_MAX:
            _SEEN_UPDATE_IDS.popitem(last=False)
        return False


@app.get("/", include_in_schema=False)
def dashboard():
    """Serves the financial dashboard frontend at the root path."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index), headers={"Cache-Control": "no-cache"})
    return {"status": "dashboard missing", "detail": "static/index.html not found"}


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """
    Receives webhook requests from the Telegram Bot API.

    Processing is synchronous (reliable on serverless, where post-response
    background work can be frozen), but guarded by an update_id idempotency
    check so Telegram's retries never double-log an expense.
    """
    # Authenticate the caller when a webhook secret is configured.
    if config.TELEGRAM_WEBHOOK_SECRET and (
        x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET
    ):
        logger.warning("Rejected webhook call with missing/invalid secret token.")
        return JSONResponse({"status": "forbidden"}, status_code=403)

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Webhook received a non-JSON body; ignoring.")
        return {"status": "ignored"}

    update_id = payload.get("update_id")
    message = payload.get("message")
    if not message:
        logger.info("Ignoring update %s: no 'message' object.", update_id)
        return {"status": "ignored"}

    sender_id = message.get("from", {}).get("id")
    if allowed_user_id and str(sender_id) != str(allowed_user_id):
        logger.warning("Unauthorized access attempt by user ID %s.", sender_id)
        return {"status": "unauthorized", "message": "You are not authorized to use this bot."}

    chat = message.get("chat")
    text = message.get("text")
    message_date_unix = message.get("date")

    if not chat or not text:
        logger.info("Ignoring update %s: no message text or chat.", update_id)
        return {"status": "ignored"}

    if _already_processed(update_id):
        logger.info("Skipping already-processed update_id=%s", update_id)
        return {"status": "duplicate"}

    chat_id = chat.get("id")

    if message_date_unix:
        date_str = timeutils.from_unix(message_date_unix).strftime(timeutils.DATE_FMT)
    else:
        date_str = timeutils.today_str()

    logger.info("Processing update_id=%s chat_id=%s", update_id, chat_id)
    try:
        agent.run_expense_flow(raw_text=text, chat_id=chat_id, current_date=date_str)
        logger.info("Successfully processed update_id=%s", update_id)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Error processing update_id=%s: %s", update_id, e)
        # Do not leak internals to the caller.
        return {"status": "error"}


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": timeutils.now().isoformat()}


@app.get("/setup-webhook")
def setup_webhook(
    url: str = Query(..., description="The HTTPS public URL of your deployment"),
    secret: str | None = Query(
        default=None,
        description="Required when TELEGRAM_WEBHOOK_SECRET is configured.",
    ),
):
    """Utility endpoint to configure the bot webhook from a browser."""
    if config.TELEGRAM_WEBHOOK_SECRET and secret != config.TELEGRAM_WEBHOOK_SECRET:
        return JSONResponse({"status": "forbidden"}, status_code=403)
    if not config.TELEGRAM_WEBHOOK_SECRET:
        logger.warning(
            "/setup-webhook called without TELEGRAM_WEBHOOK_SECRET set - "
            "this endpoint is unauthenticated. Set the env var to secure it."
        )

    webhook_url = url.strip()
    if not webhook_url.endswith("/webhook"):
        webhook_url += "webhook" if webhook_url.endswith("/") else "/webhook"

    success = telegram_utils.set_telegram_webhook(webhook_url)
    if success:
        return {"status": "success", "message": f"Telegram webhook registered to: {webhook_url}"}
    return {"status": "error", "message": "Failed to register webhook. Check server logs."}
