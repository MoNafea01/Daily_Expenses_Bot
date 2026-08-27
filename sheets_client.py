import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import config

logger = logging.getLogger(__name__)

# Scopes needed for Google Sheets API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheets_client():
    """Initializes and returns the authorized gspread client."""
    creds = Credentials.from_service_account_info(
        config.GOOGLE_SERVICE_ACCOUNT_JSON,
        scopes=SCOPES
    )
    return gspread.authorize(creds)

def get_worksheet():
    """Gets the first worksheet (Sheet1) of the spreadsheet. Initializes headers if empty."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
    worksheet = spreadsheet.get_worksheet(0)
    
    # Check if we need to initialize headers
    try:
        headers = worksheet.row_values(1)
        if not headers:
            initialize_headers(worksheet)
    except Exception:
        initialize_headers(worksheet)
        
    return worksheet

def initialize_headers(worksheet):
    """Initializes sheet headers if sheet is blank."""
    headers = ["Date", "Amount", "Currency", "Description", "Category", "Payment Method", "Raw Text", "Created At"]
    worksheet.insert_row(headers, 1)
    logger.info("Initialized sheet headers.")

def append_expense(expense_dict: dict, raw_text: str) -> list:
    """
    Appends an expense record to the sheet.
    Returns the exact row representation list that was appended.
    """
    worksheet = get_worksheet()
    
    date_str = expense_dict.get("date") or datetime.now().strftime("%Y-%m-%d")
    amount = float(expense_dict.get("amount") or 0.0)
    currency = expense_dict.get("currency") or "EGP"
    description = expense_dict.get("description") or "Unspecified"
    category = expense_dict.get("category") or "Other"
    payment_method = expense_dict.get("payment_method") or "Cash"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    row_data = [
        date_str,
        amount,
        currency,
        description,
        category,
        payment_method,
        raw_text,
        created_at
    ]
    
    # Append the row
    worksheet.append_row(row_data, value_input_option="USER_ENTERED")
    logger.info(f"Successfully appended row to sheets: {row_data}")
    return row_data

def get_last_record() -> list:
    """
    Retrieves the last row from the worksheet.
    Returns a list representing the row values, or empty list if only header exists.
    """
    worksheet = get_worksheet()
    records = worksheet.get_all_values()
    if len(records) <= 1:
        return []
    return records[-1]

def verify_expense_write(expected_row: list) -> bool:
    """
    Retrieves the last written row and checks if it matches the expected_row.
    Matches first 6 values (Date, Amount, Currency, Description, Category, Payment Method)
    and Raw Text (value 7). Ignores Created At timestamp (value 8) to avoid timezone/clock mismatch issues.
    """
    last_row = get_last_record()
    if not last_row or len(last_row) < 7:
        return False
    
    # Compare Date, Amount (converted to float for numerical comparison), Currency, Description, Category, Payment Method, Raw Text
    try:
        # Check date
        if last_row[0] != str(expected_row[0]):
            return False
        # Check numerical amount
        if float(last_row[1]) != float(expected_row[1]):
            return False
        # Check currency, description, category, payment method, raw text
        for i in [2, 3, 4, 5, 6]:
            if last_row[i] != str(expected_row[i]):
                return False
        return True
    except Exception as e:
        logger.error(f"Error during sheet write verification: {e}")
        return False
