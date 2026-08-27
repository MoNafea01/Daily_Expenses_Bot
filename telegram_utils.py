import logging
import httpx
import config

logger = logging.getLogger(__name__)

def send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """
    Sends a message to the specified Telegram chat_id.
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        logger.info(f"Sending message to Telegram chat {chat_id}: '{text[:100]}...'")
        response = httpx.post(url, json=payload, timeout=10.0)
        if response.status_code == 200:
            logger.info("Telegram message sent successfully.")
            return True
        else:
            logger.error(f"Failed to send Telegram message: Status {response.status_code}, Body: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False

def set_telegram_webhook(webhook_url: str) -> bool:
    """
    Sets the webhook URL for the Telegram bot.
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/setWebhook"
    payload = {
        "url": webhook_url
    }
    try:
        logger.info(f"Setting Telegram webhook to {webhook_url}")
        response = httpx.post(url, json=payload, timeout=10.0)
        if response.status_code == 200:
            logger.info(f"Webhook set successfully: {response.json()}")
            return True
        else:
            logger.error(f"Failed to set webhook: Status {response.status_code}, Body: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return False
