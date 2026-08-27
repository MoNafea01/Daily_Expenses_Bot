# 💸 Daily Expenses Bot

A natural language Telegram bot that structures your daily expenses using **FastAPI**, **LangGraph**, and **DSPy** with **Groq**, persists them in **Google Sheets**, and double-checks write operations before notifying you. 

Designed for seamless integration with local financial dashboards, such as Obsidian, via Google Sheets.

---

## 🛠️ Architecture

1. **User Message:** Send a natural language expense report (e.g., `"spent 120 EGP on a taxi today"`) to your Telegram Bot.
2. **FastAPI Webhook:** Receives the Telegram payload, acknowledges it with `200 OK` instantly to prevent Telegram timeouts, and queues the execution as a background task.
3. **Conversational LangGraph Worker (multi-turn):**
   - **Load Memory:** Fetches prior conversation history for the `chat_id` from the `Memory` worksheet in your Google Sheet so details can be carried across turns.
   - **Route & Extract:** A **DSPy + Groq (`openai/gpt-oss-20b`) router** looks at the full conversation and decides whether this is an expense log (or answers completing it), or just casual chat:
     - **Just chatting** → replies conversationally and saves the dialogue.
     - **Incomplete expense** (e.g. only "I ate kabab") → asks in the user's language (Arabic/English) for the missing mandatory fields (date, amount, category) and remembers the partial info.
     - **Complete expense** → extracts all fields, resolving relative dates (like `"yesterday"`, `"last Friday"`).
   - **Persist & Verify:** Appends the complete record to your Google Sheets database, then double-checks the write by querying the spreadsheet and comparing the last row with the input values.
   - **Clear Memory:** Resets the conversation history once an expense is successfully recorded.
   - **Respond:** Sends a beautiful, formatted Markdown confirmation back to you on Telegram.

---

## ⚙️ Prerequisites & Environment Configuration

Create a `.env` file in the root directory (one is already initialized for you) with the following variables:

```ini
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
GROQ_API_KEY="your_groq_api_key"
GOOGLE_SHEET_ID="your_google_sheet_id"
GOOGLE_SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
```

*Note: Ensure the Google Service Account email has **Editor** access to your Google Sheet.*

The bot uses **two worksheets** in the same spreadsheet:
- `Sheet1` (or the first sheet): stores logged expense records.
- `Memory`: stores per-`chat_id` conversation history (JSON) to support multi-turn expensing. It is created automatically on first use.

### Budget Categories

Every expense is classified into one of **9 budget categories** (canonical Arabic names; the bot accepts many Arabic/English aliases and normalizes them automatically):

| Category | Budget share | Examples |
| :--- | :--- | :--- |
| استثمار | 25% | Investment, stocks, funds |
| طوارئ | 15% | Emergency, insurance |
| ادخار | 15% | Savings, deposits |
| أكل | 15% | Food, restaurants, coffee |
| مواصلات | 5% | Transport, taxi, fuel |
| رفاهيات | 10% | Entertainment, games, hobbies |
| ملابس | 5% | Clothing, shoes |
| مرافق | 5% | Utilities, electricity, water |
| إنترنت | 5% | Internet, data, WiFi |

When a category is needed and hasn't been determined, the bot lists these options so you can type one exactly.

---

## 🚀 Local Development & Testing

### 1. Installation
Set up a Python virtual environment and install the required dependencies:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Verify Your Configuration
Run the integration test script to verify DSPy extraction, Google Sheets connection, and the LangGraph workflow:
```bash
python test_workflow.py
```
This script will mock a Telegram message send, verify sheets logging, and output a preview of the formatted Markdown response.

### 3. Run FastAPI Server Locally
Start the server using `uvicorn`:
```bash
uvicorn main:app --reload
```
The server will start at `http://127.0.0.1:8000`. You can inspect the health check at `http://127.0.0.1:8000/health`.

---

## ☁️ Deploying to Vercel

1. Push your repository to **GitHub** or **GitLab**.
2. Go to the [Vercel Dashboard](https://vercel.com/) and create a **New Project**.
3. Import your repository.
4. Expand **Environment Variables** and add all variables from your `.env` file:
   - `TELEGRAM_BOT_TOKEN`
   - `GROQ_API_KEY`
   - `GOOGLE_SHEET_ID`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`
5. Click **Deploy**. Vercel will automatically read `vercel.json` and build your FastAPI server as a serverless function.

---

## 🔗 Telegram Webhook

Register Webhook
Once your Vercel project is live, copy your deployment URL (e.g., `https://daily-expenses-bot.vercel.app`).
Register this URL with Telegram by opening your web browser and navigating to:
```text
https://<your-vercel-app-url>/setup-webhook?url=https://<your-vercel-app-url>/webhook
```
Example: `https://daily-expenses-bot.vercel.app/setup-webhook?url=https://daily-expenses-bot.vercel.app/webhook`

If successful, the page will output:
`{"status":"success","message":"Telegram webhook has been registered to: https://.../webhook"}`


---

## 📓 Connecting to Obsidian

To integrate these entries with your financial dashboard at `D:\Obsidian Vault\Financial Dashboard.md` when an internet connection is available:
1. Install an Obsidian community plugin such as **Google Sheets Link** or **Local REST API** that syncs with remote worksheets.
2. Alternatively, you can use the **Dataview** plugin with a custom JS script to pull Google Sheets data dynamically when Obsidian loads:
   - Configure a Google Sheets API endpoint or fetch CSV/JSON format from your published sheet URL (or through the Sheets API using a custom script).
   - Use this fetched data to populate your `Financial Dashboard.md` charts and summaries.
