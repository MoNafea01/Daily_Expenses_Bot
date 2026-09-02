import logging
import time

import httpx

import config

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def _post_with_retry(url: str, payload: dict, *, tries: int = 3, base_delay: float = 0.6):
    """POSTs to the Telegram Bot API with exponential backoff on transient errors."""
    for attempt in range(1, tries + 1):
        try:
            response = httpx.post(url, json=payload, timeout=10.0)
        except httpx.RequestError as e:
            if attempt == tries:
                raise
            logger.warning("Telegram request error (%s); retry %d/%d", e, attempt, tries)
            time.sleep(base_delay * (2 ** (attempt - 1)))
            continue

        if response.status_code == 200:
            return response
        if response.status_code in _TRANSIENT_STATUS and attempt < tries:
            logger.warning(
                "Telegram API %s; retry %d/%d", response.status_code, attempt, tries
            )
            time.sleep(base_delay * (2 ** (attempt - 1)))
            continue
        return response


def send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Sends a message to the specified Telegram chat_id. Returns True on success."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        logger.info("Sending message to Telegram chat %s: %r", chat_id, text[:100])
        response = _post_with_retry(url, payload)
        if response.status_code == 200:
            logger.info("Telegram message sent successfully.")
            return True
        logger.error(
            "Failed to send Telegram message: Status %s, Body: %s",
            response.status_code, response.text,
        )
        return False
    except Exception as e:
        logger.error("Error sending Telegram message: %s", e)
        return False


def set_telegram_webhook(webhook_url: str) -> bool:
    """Registers the webhook URL with Telegram. When TELEGRAM_WEBHOOK_SECRET is
    configured it is sent as `secret_token`, so Telegram will include it in the
    `X-Telegram-Bot-Api-Secret-Token` header of every webhook call."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/setWebhook"
    payload = {"url": webhook_url}
    if config.TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = config.TELEGRAM_WEBHOOK_SECRET
    try:
        logger.info("Setting Telegram webhook to %s", webhook_url)
        response = _post_with_retry(url, payload)
        if response.status_code == 200:
            logger.info("Webhook set successfully: %s", response.json())
            return True
        logger.error(
            "Failed to set webhook: Status %s, Body: %s",
            response.status_code, response.text,
        )
        return False
    except Exception as e:
        logger.error("Error setting webhook: %s", e)
        return False
