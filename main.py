import os
import logging
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import agent
import telegram_utils
import config

# Configure logging to standard output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
allowed_user_id = config.ALLOWED_USER_ID

app = FastAPI(
    title="Daily Expenses Bot Server",
    description="FastAPI Webhook Server that parses expense records using LangGraph, DSPy, and Groq, then persists them in Google Sheets.",
    version="1.0.0"
)

# Serve the financial dashboard frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.warning("Static directory not found: %s", STATIC_DIR)


@app.get("/", include_in_schema=False)
def dashboard():
    """Serves the financial dashboard frontend at the root path."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "dashboard missing", "detail": "static/index.html not found"}

def run_agent_in_background(text: str, chat_id: int, date_str: str):
    """
    Background worker function that runs the LangGraph agent flow.
    """
    try:
        logger.info(f"Background task started for chat {chat_id}")
        agent.run_expense_flow(raw_text=text, chat_id=chat_id, current_date=date_str)
        logger.info(f"Background task finished successfully for chat {chat_id}")
    except Exception as e:
        logger.error(f"Background task failed for chat {chat_id}: {e}")

@app.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives webhook requests from the Telegram Bot API.
    Acks immediately to avoid timeouts, and processes the request in a FastAPI BackgroundTask.
    """
    try:
        payload = await request.json()
        logger.info(f"Received webhook payload: {payload}")
        
        # Check if the update contains a text message
        message = payload.get("message")
        if not message:
            # Could be a channel post, callback query, edited message, etc.
            logger.info("Ignoring update: 'message' object not found in payload.")
            return {"status": "ignored"}
        
        sender_id = message.get("from", {}).get("id")
        if allowed_user_id and str(sender_id) != str(allowed_user_id):
            logger.warning(f"Unauthorized access attempt by user ID {sender_id}. Allowed user ID is {allowed_user_id}.")
            return {"status": "unauthorized", "message": "You are not authorized to use this bot."}   
        
        chat = message.get("chat")
        text = message.get("text")
        message_date_unix = message.get("date")
        
        if not chat or not text:
            logger.info("Ignoring update: message text or chat not found.")
            return {"status": "ignored"}
            
        chat_id = chat.get("id")
        
        # Resolve message date
        if message_date_unix:
            message_date = datetime.fromtimestamp(message_date_unix)
            date_str = message_date.strftime("%Y-%m-%d")
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Processing text for chat_id={chat_id}, text='{text}'")
        agent.run_expense_flow(raw_text=text, chat_id=chat_id, current_date=date_str)
        logger.info(f"Successfully processed flow for chat_id={chat_id}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error handling webhook request: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/health")
def health_check():
    """
    Health check endpoint for Vercel.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/setup-webhook")
def setup_webhook(url: str = Query(..., description="The HTTPS public URL of your server deployment (e.g., https://your-app.onrender.com/webhook)")):
    """
    Utility endpoint to configure the bot webhook easily via browser.
    """
    # Clean and normalise url
    webhook_url = url.strip()
    if not webhook_url.endswith("/webhook"):
        if webhook_url.endswith("/"):
            webhook_url += "webhook"
        else:
            webhook_url += "/webhook"
            
    success = telegram_utils.set_telegram_webhook(webhook_url)
    if success:
        return {"status": "success", "message": f"Telegram webhook has been registered to: {webhook_url}"}
    else:
        return {"status": "error", "message": f"Failed to register webhook. Check server logs."}
    