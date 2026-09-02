import logging
import json
import re
import time

import gspread
from google.oauth2.service_account import Credentials

import config
import timeutils

logger = logging.getLogger(__name__)

# Scopes needed for Google Sheets API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPENSE_HEADERS = [
    "Date", "Amount", "Currency", "Description",
    "Category", "Payment Method", "Raw Text", "Created At",
]
MEMORY_HEADERS = ["ChatID", "HistoryJSON", "LastUpdated"]

# Module-level caches. gspread clients are cheap to hold and expensive to
# recreate (each rebuild does an OAuth token exchange), and a single expense
# flow touches the spreadsheet ~6 times. Cache the authorized client and the
# opened spreadsheet; worksheets are looked up from the cached spreadsheet.
_client = None
_spreadsheet = None


def _retry(fn, *, tries: int = 3, base_delay: float = 0.6):
    """Call `fn` with exponential backoff on transient Google API errors
    (429 rate limit, 5xx). Re-raises the last error if all attempts fail."""
    last_exc = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except gspread.exceptions.APIError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status not in (429, 500, 502, 503, 504) or attempt == tries:
                raise
            last_exc = e
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Sheets API %s on attempt %d/%d; retrying in %.1fs",
                status, attempt, tries, delay,
            )
            time.sleep(delay)
    if last_exc:
        raise last_exc


def get_sheets_client():
    """Returns a cached authorized gspread client."""
    global _client
    if _client is None:
        creds = Credentials.from_service_account_info(
            config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet():
    """Returns the cached opened spreadsheet."""
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = _retry(
            lambda: get_sheets_client().open_by_key(config.GOOGLE_SHEET_ID)
        )
    return _spreadsheet


def reset_cache():
    """Drops the cached client/spreadsheet. Used by tests and as a recovery
    hook if a cached handle goes stale."""
    global _client, _spreadsheet
    _client = None
    _spreadsheet = None


def get_worksheet():
    """Gets the first worksheet of the spreadsheet, initializing headers if empty."""
    worksheet = _retry(lambda: get_spreadsheet().get_worksheet(0))

    try:
        headers = _retry(lambda: worksheet.row_values(1))
        if not headers:
            initialize_headers(worksheet)
    except gspread.exceptions.APIError:
        raise
    except Exception:
        initialize_headers(worksheet)

    return worksheet


def initialize_headers(worksheet):
    """Initializes sheet headers if sheet is blank."""
    _retry(lambda: worksheet.insert_row(EXPENSE_HEADERS, 1))
    logger.info("Initialized sheet headers.")


def _to_float(value) -> float:
    """Parses a number that may carry thousands separators (Sheets can return
    '1,000' when value_input_option='USER_ENTERED')."""
    return float(re.sub(r"[,\s]", "", str(value)))


def append_expense(expense_dict: dict, raw_text: str) -> dict:
    """
    Appends an expense record to the sheet.

    Returns a dict with the appended `row` (list of 8 values) and the 1-indexed
    `row_number` it landed on, so verification can read back the exact row
    instead of guessing it is "the last one".
    """
    worksheet = get_worksheet()

    date_str = expense_dict.get("date") or timeutils.today_str()
    amount = float(expense_dict.get("amount") or 0.0)
    currency = expense_dict.get("currency") or "EGP"
    description = expense_dict.get("description") or "Unspecified"
    category = expense_dict.get("category") or "Other"
    payment_method = expense_dict.get("payment_method") or "Cash"
    created_at = timeutils.timestamp_str()

    row_data = [
        date_str, amount, currency, description,
        category, payment_method, raw_text, created_at,
    ]

    resp = _retry(
        lambda: worksheet.append_row(
            row_data,
            value_input_option="USER_ENTERED",
            table_range="A1",
        )
    )

    row_number = _parse_updated_row_number(resp)
    logger.info("Appended expense row %s: %s", row_number, row_data)
    return {"row": row_data, "row_number": row_number}


def _parse_updated_row_number(append_response: dict):
    """Extracts the row number from an append_row API response
    (updates.updatedRange like 'Sheet1!A7:H7')."""
    try:
        updated_range = append_response["updates"]["updatedRange"]
        m = re.search(r"![A-Z]+(\d+):", updated_range)
        if m:
            return int(m.group(1))
    except (KeyError, TypeError):
        pass
    return None


def get_last_record() -> list:
    """Retrieves the last row from the worksheet, or [] if only the header exists."""
    worksheet = get_worksheet()
    records = _retry(lambda: worksheet.get_all_values())
    if len(records) <= 1:
        return []
    return records[-1]


def get_row(row_number: int) -> list:
    """Retrieves a specific 1-indexed row's values, or [] if unavailable."""
    worksheet = get_worksheet()
    try:
        return _retry(lambda: worksheet.row_values(row_number))
    except Exception as e:
        logger.error("Could not read row %s: %s", row_number, e)
        return []


def verify_expense_write(append_result) -> bool:
    """
    Confirms the expense we just appended is actually in the sheet.

    Reads back the specific row returned by `append_expense` (falling back to the
    last row for older callers/None), then anchors the check on the fields Google
    Sheets will not silently reformat: Raw Text (a long unique string), the
    numeric Amount, Currency, Description, Category and Payment Method. The Date
    is only logged if it differs, because USER_ENTERED input can be reformatted
    or stored as a serial by Sheets.
    """
    if isinstance(append_result, dict):
        expected_row = append_result.get("row") or []
        row_number = append_result.get("row_number")
    else:
        # Backwards compatibility: a plain row list was passed.
        expected_row = append_result or []
        row_number = None

    if not expected_row or len(expected_row) < 7:
        return False

    actual = get_row(row_number) if row_number else get_last_record()
    if not actual or len(actual) < 7:
        return False

    try:
        if _to_float(actual[1]) != _to_float(expected_row[1]):
            logger.warning("Verify: amount mismatch %r vs %r", actual[1], expected_row[1])
            return False
        for i in (2, 3, 4, 5, 6):  # currency, description, category, payment method, raw text
            if str(actual[i]).strip() != str(expected_row[i]).strip():
                logger.warning(
                    "Verify: field %d mismatch %r vs %r", i, actual[i], expected_row[i]
                )
                return False
        if str(actual[0]).strip() != str(expected_row[0]).strip():
            logger.warning(
                "Verify: date reformatted by Sheets (%r vs %r) - accepted",
                actual[0], expected_row[0],
            )
        return True
    except Exception as e:
        logger.error("Error during sheet write verification: %s", e)
        return False


# ------------------------------------------------------------------ #
#  Conversation memory                                               #
# ------------------------------------------------------------------ #

def get_memory_worksheet():
    """Gets or creates the 'Memory' worksheet for conversation history."""
    spreadsheet = get_spreadsheet()
    try:
        return _retry(lambda: spreadsheet.worksheet("Memory"))
    except gspread.exceptions.WorksheetNotFound:
        worksheet = _retry(
            lambda: spreadsheet.add_worksheet(title="Memory", rows=1000, cols=3)
        )
        _retry(lambda: worksheet.insert_row(MEMORY_HEADERS, 1))
        logger.info("Created 'Memory' worksheet and initialized headers.")
        return worksheet


def _find_chat_row(records: list, chat_id_str: str) -> int:
    """Returns the 1-indexed row for a chat id, or -1 if not present."""
    for idx, row in enumerate(records):
        if row and row[0] == chat_id_str:
            return idx + 1
    return -1


def get_conversation_history(chat_id: int) -> list:
    """Retrieves conversation history list for a chat_id."""
    try:
        worksheet = get_memory_worksheet()
        records = _retry(lambda: worksheet.get_all_values())
        chat_id_str = str(chat_id)
        for row in records[1:]:
            if row and row[0] == chat_id_str:
                return json.loads(row[1]) if row[1] else []
        return []
    except Exception as e:
        logger.error("Error getting conversation history for chat %s: %s", chat_id, e)
        return []


def save_conversation_history(chat_id: int, history: list) -> bool:
    """Saves conversation history list for a chat_id. Returns True on success."""
    try:
        worksheet = get_memory_worksheet()
        records = _retry(lambda: worksheet.get_all_values())

        chat_id_str = str(chat_id)
        history_json = json.dumps(history, ensure_ascii=False)
        now_str = timeutils.timestamp_str()
        row_idx = _find_chat_row(records, chat_id_str)

        if row_idx != -1:
            # Single batched write for columns B (HistoryJSON) and C (LastUpdated).
            _retry(lambda: worksheet.update(
                range_name=f"B{row_idx}:C{row_idx}",
                values=[[history_json, now_str]],
            ))
            logger.info("Updated conversation history in sheet for chat %s.", chat_id)
        else:
            _retry(lambda: worksheet.append_row(
                [chat_id_str, history_json, now_str],
                value_input_option="USER_ENTERED",
                table_range="A1",
            ))
            logger.info("Created new conversation history row for chat %s.", chat_id)
        return True
    except Exception as e:
        logger.error("Error saving conversation history for chat %s: %s", chat_id, e)
        return False


def clear_conversation_history(chat_id: int) -> bool:
    """Clears conversation history for a chat_id by resetting its JSON to []."""
    try:
        worksheet = get_memory_worksheet()
        records = _retry(lambda: worksheet.get_all_values())

        chat_id_str = str(chat_id)
        row_idx = _find_chat_row(records, chat_id_str)
        if row_idx != -1:
            _retry(lambda: worksheet.update(
                range_name=f"B{row_idx}:C{row_idx}",
                values=[["[]", timeutils.timestamp_str()]],
            ))
            logger.info("Cleared conversation history in sheet for chat %s.", chat_id)
        return True
    except Exception as e:
        logger.error("Error clearing conversation history for chat %s: %s", chat_id, e)
        return False
