import logging
import json
import threading
from typing import Optional, List
import dspy
from pydantic import BaseModel, Field
import config
import timeutils

logger = logging.getLogger(__name__)

# Canonical budget categories (Arabic) with their budget allocation ratios.
# The percentage is metadata kept for future reporting; only the category NAMES
# are injected into prompts (the user chose to show categories only, not amounts).
CATEGORIES = {
    "استثمار": 0.25,   # Investment
    "طوارئ": 0.15,     # Emergency
    "ادخار": 0.15,     # Savings
    "أكل": 0.15,       # Food
    "مواصلات": 0.05,   # Transport
    "رفاهيات": 0.10,   # Luxury / Entertainment
    "ملابس": 0.05,     # Clothing
    "مرافق": 0.05,     # Utilities
    "إنترنت": 0.05,    # Internet
}

# DSPy language model (Groq via LiteLLM). Configured lazily on first use so that
# importing this module - e.g. to reach the pure helpers below, or for tests -
# does not require a live API key or a network call.
_LM_MODEL = "groq/openai/gpt-oss-20b"
_lm_lock = threading.Lock()
_lm_configured = False


def _ensure_lm() -> None:
    global _lm_configured
    if _lm_configured:
        return
    with _lm_lock:
        if _lm_configured:
            return
        lm = dspy.LM(_LM_MODEL, api_key=config.GROQ_API_KEY)
        dspy.configure(lm=lm)
        _lm_configured = True
        logger.info("Configured DSPy with Groq LM (%s)", _LM_MODEL)

# Define the Pydantic model for unified routing & extraction output
class RouterOutput(BaseModel):
    is_expense_log: bool = Field(
        description="True if the user is trying to log an expense or providing answers to collect missing details. False if they are just chatting."
    )
    chat_response: Optional[str] = Field(
        description="Friendly chat response if is_expense_log is False (normal conversation). Leave empty if logging an expense."
    )

    # Extracted Expense Fields (Optional because they might be collected across turns)
    date: Optional[str] = Field(
        description="YYYY-MM-DD. Resolve relative dates (today, yesterday) based on current_date. If the user does not mention any date at all, default to current_date."
    )
    amount: Optional[float] = Field(description="Numeric amount of expense.")
    category: Optional[str] = Field(
        description=f"The budget category of the expense. Must be exactly one of these valid categories: {', '.join(CATEGORIES.keys())}. Use the closest category (e.g. restaurants/coffee -> 'أكل', taxi/fuel -> 'مواصلات', clothes/shoes -> 'ملابس', electricity/water bill -> 'مرافق', internet/data -> 'إنترنت', games/cinema/hobbies -> 'رفاهيات')."
    )
    description: Optional[str] = Field(description="Description of purchase.")
    currency: Optional[str] = Field(description="Currency. Default is EGP.")
    payment_method: Optional[str] = Field(description="Payment method. Default is Cash.")

    # Missing Fields Prompt
    missing_fields_prompt: Optional[str] = Field(
        description=f"If is_expense_log is True but any of the mandatory fields (date, amount, category) are missing, generate a friendly, natural message in the user's language (Arabic or English) asking for the missing fields. If the category is missing, list these valid category options in the message so the user can type one of them exactly: {', '.join(CATEGORIES.keys())}. If all mandatory fields are present, leave this empty."
    )

# Define the DSPy Signature
class RouterSignature(dspy.Signature):
    """
    Given the full conversation history between a user and an expense-tracking bot,
    decide the appropriate action:
    1. If the user is trying to log an expense (or is answering follow-up questions to
       complete an expense), set is_expense_log to True and extract as many expense fields
       as are known so far. Fill in missing values carried over from earlier turns using the
       conversation history.
    2. If the user is just chatting (greeting, asking questions, off-topic), set
       is_expense_log to False and provide a friendly chat_response.
    Resolve relative dates like 'today' or 'yesterday' using the provided current_date.
    If no date is mentioned at all, default the date field to current_date.
    """
    conversation: str = dspy.InputField(desc="JSON string of the full conversation history (list of {role, content} messages).")
    current_date: str = dspy.InputField(desc="The current date in YYYY-MM-DD format, used as the anchor for resolving relative dates.")
    output: RouterOutput = dspy.OutputField(desc="Structured routing and extraction result.")

# Dedicated model for the final complete expense extraction (all fields required)
class FinalExpense(BaseModel):
    date: str = Field(
        description="ISO 8601 formatted date (YYYY-MM-DD) when the expense occurred. Resolve relative dates (today, yesterday) using current_date. Default to current_date if no date is mentioned."
    )
    amount: float = Field(description="The numerical amount of the expense (e.g. 150.0). Always output a positive number.")
    currency: str = Field(description="The currency code (e.g. EGP, USD, EUR). Default to 'EGP'.")
    description: str = Field(description="A concise description of what was purchased. Use details from the conversation (e.g. 'SSD from Bostan Mall', 'كفتة'). Do not include the amount or date.")
    category: str = Field(description=f"The budget category of the expense. Must be exactly one of these valid categories: {', '.join(CATEGORIES.keys())}. Use the closest category (e.g. restaurants/coffee -> 'أكل', taxi/fuel -> 'مواصلات', clothes/shoes -> 'ملابس', electricity/water bill -> 'مرافق', internet/data -> 'إنترنت', games/cinema/hobbies -> 'رفاهيات').")
    payment_method: str = Field(description="The payment method. Must be one of: Cash, Card, Wallet, Instapay, Bank, Other. Default to 'Cash'.")

# Define the DSPy Signature for the final full extraction
class FinalExpenseSignature(dspy.Signature):
    """
    Given the full conversation history between a user and an expense-tracking bot,
    extract the COMPLETE expense record. The user's details may be spread across multiple
    messages (e.g. the amount in one message, the date and description in another).
    Combine all information from the whole conversation to fill every field.
    Resolve relative dates (today, yesterday) using the provided current_date.
    """
    conversation: str = dspy.InputField(desc="JSON string of the full conversation history (list of {role, content} messages).")
    current_date: str = dspy.InputField(desc="The current date in YYYY-MM-DD format, used as the anchor for resolving relative dates.")
    expense: FinalExpense = dspy.OutputField(desc="The complete structured expense record.")

# Map aliases (Arabic and English) to the canonical category name.
# Add as many realistic variants as possible so the LLM's output and user input
# both normalize cleanly to one of the 9 categories.
CATEGORY_ALIASES = {
    # استثمار (Investment)
    "استثمار": "استثمار",
    "ستثمار": "استثمار",
    "investment": "استثمار",
    "invest": "استثمار",
    "investing": "استثمار",
    "stocks": "استثمار",
    "shares": "استثمار",
    "اسهم": "استثمار",
    "بورصة": "استثمار",
    "حافظات": "استثمار",
    "صندوق": "استثمار",
    "fund": "استثمار",
    # طوارئ (Emergency)
    "طوارئ": "طوارئ",
    "emergency": "طوارئ",
    "urgent": "طوارئ",
    "حالات طارئة": "طوارئ",
    "طارئ": "طوارئ",
    "crash": "طوارئ",
    "insurance": "طوارئ",
    "تأمين": "طوارئ",
    # ادخار (Savings)
    "ادخار": "ادخار",
    "savings": "ادخار",
    "saving": "ادخار",
    "save": "ادخار",
    "حفظ": "ادخار",
    "وديعة": "ادخار",
    "deposit": "ادخار",
    "needs saving": "ادخار",
    # أكل (Food)
    "أكل": "أكل",
    "اكل": "أكل",
    "طعام": "أكل",
    "اكلا": "أكل",
    "food": "أكل",
    "eating": "أكل",
    "meal": "أكل",
    "restaurant": "أكل",
    "مطعم": "أكل",
    "غداء": "أكل",
    "عشاء": "أكل",
    "فطار": "أكل",
    "قهوة": "أكل",
    "شاي": "أكل",
    "coffee": "أكل",
    "burger": "أكل",
    "كفتة": "أكل",
    "سناك": "أكل",
    # مواصلات (Transport)
    "مواصلات": "مواصلات",
    "transport": "مواصلات",
    "transportation": "مواصلات",
    "transit": "مواصلات",
    "taxi": "مواصلات",
    "اتوبيس": "مواصلات",
    "اوبر": "مواصلات",
    "uber": "مواصلات",
    "بنزين": "مواصلات",
    "غاز": "مواصلات",
    "bus": "مواصلات",
    "مترو": "مواصلات",
    "مواصلة": "مواصلات",
    "باص": "مواصلات",
    "عربية": "مواصلات",
    "سيارة": "مواصلات",
    "شاحنة": "مواصلات",
    "قطار": "مواصلات",
    "طيران": "مواصلات",
    "سفر": "مواصلات",
    # رفاهيات (Luxury / Entertainment)
    "رفاهيات": "رفاهيات",
    "luxury": "رفاهيات",
    "entertainment": "رفاهيات",
    "ترفيه": "رفاهيات",
    "مصاريف شخصية": "رفاهيات",
    "fun": "رفاهيات",
    "gaming": "رفاهيات",
    "لعبة": "رفاهيات",
    "لعبة": "رفاهيات",
    "game": "رفاهيات",
    "سينما": "رفاهيات",
    "cinema": "رفاهيات",
    "هواية": "رفاهيات",
    "hobby": "رفاهيات",
    "هدية": "رفاهيات",
    "gift": "رفاهيات",
    # ملابس (Clothing)
    "ملابس": "ملابس",
    "clothing": "ملابس",
    "clothes": "ملابس",
    "cloth": "ملابس",
    "ملبس": "ملابس",
    "حذاء": "ملابس",
    "shoes": "ملابس",
    "اخذية": "ملابس",
    "قميص": "ملابس",
    "جاكيت": "ملابس",
    "بنطال": "ملابس",
    "فستان": "ملابس",
    "dress": "ملابس",
    "shirt": "ملابس",
    "بنطلون": "ملابس",
    "قميص": "ملابس",
    "هدوم": "ملابس",
    "ثياب": "ملابس",
    "جنز": "ملابس",
    "jeans": "ملابس",
    # مرافق (Utilities)
    "مرافق": "مرافق",
    "utilities": "مرافق",
    "utility": "مرافق",
    "فواتير": "مرافق",
    "فاتورة": "مرافق",
    "bill": "مرافق",
    "كهرباء": "مرافق",
    "مياه": "مرافق",
    "غاز المنزل": "مرافق",
    "electricity": "مرافق",
    "water": "مرافق",
    "صيانة": "مرافق",
    "maintenance": "مرافق",
    # إنترنت (Internet)
    "إنترنت": "إنترنت",
    "انترنت": "إنترنت",
    "internet": "إنترنت",
    "net": "إنترنت",
    "شبكة": "إنترنت",
    "واي فاي": "إنترنت",
    "وايفاي": "إنترنت",
    "wifi": "إنترنت",
    "باقة": "إنترنت",
    "data": "إنترنت",
    "بيانات": "إنترنت",
    # Legacy / extra categories -> map to the closest budget category
    "تسوق": "ملابس",
    "shopping": "ملابس",
    "صحة": "طوارئ",
    "health": "طوارئ",
    "تعليم": "استثمار",
    "education": "استثمار",
    "أخرى": "أخرى",
    "other": "أخرى",
}

# Bucket for anything that cannot be mapped to one of the 9 budget categories.
# The dashboard renders this row too (with a 0 budget), so miscategorized spend
# stays visible instead of silently vanishing from the budget totals.
FALLBACK_CATEGORY = "أخرى"

# Every value that may legitimately be written to the sheet's Category column.
KNOWN_CATEGORIES = list(CATEGORIES.keys()) + [FALLBACK_CATEGORY]

def get_category_options_text() -> str:
    """Returns a readable list of the valid categories (names only) for prompt injection."""
    return " / ".join(CATEGORIES.keys())

def normalize_category(category: Optional[str]) -> Optional[str]:
    """
    Maps an Arabic/English category alias (or a combined 'Alias/English' string)
    to one of the canonical budget categories. Returns None for empty input, and
    FALLBACK_CATEGORY ("أخرى") when the value cannot be recognized - so the sheet
    never receives an arbitrary string the dashboard cannot account for.
    """
    if not category:
        return None
    key = category.strip().lower()
    # Handle a combined string like "اكل/Food" -> take the first part
    if "/" in key:
        key = key.split("/")[0].strip()
    # Try the exact key first
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    # Try removing the Arabic definite article "ال" (e.g. الكهرباء -> كهرباء)
    stripped = key
    if stripped.startswith("ال") and len(stripped) > 3:
        stripped = stripped[2:]
    return CATEGORY_ALIASES.get(stripped, FALLBACK_CATEGORY)

def run_router(conversation: list, current_date_str: str = None) -> RouterOutput:
    """
    Uses DSPy Predict to classify the conversation and extract expense fields
    (or generate a chat response) based on the full conversation history.
    """
    _ensure_lm()
    if not current_date_str:
        current_date_str = timeutils.today_str()

    conversation_str = json.dumps(conversation, ensure_ascii=False)

    predictor = dspy.Predict(RouterSignature)

    try:
        logger.info(f"Running router with {len(conversation)} messages relative to date '{current_date_str}'")
        result = predictor(conversation=conversation_str, current_date=current_date_str)
        output = result.output

        # Only normalize category when logging an expense
        if output.is_expense_log and output.category:
            output.category = normalize_category(output.category)

        logger.info(f"DSPy routing result: {output.model_dump()}")
        return output
    except Exception as e:
        logger.error(f"DSPy routing failed: {e}")
        raise e


def extract_final_expense(conversation: list, current_date_str: str = None) -> FinalExpense:
    """
    Performs a dedicated, complete expense extraction over the full conversation history.
    This is more reliable than trusting fields to be carried over on the final routing turn,
    because it combines all information spread across all messages into one record.
    """
    _ensure_lm()
    if not current_date_str:
        current_date_str = timeutils.today_str()

    conversation_str = json.dumps(conversation, ensure_ascii=False)
    predictor = dspy.Predict(FinalExpenseSignature)

    try:
        logger.info(f"Extracting final expense from {len(conversation)} messages relative to date '{current_date_str}'")
        result = predictor(conversation=conversation_str, current_date=current_date_str)
        expense = result.expense
        expense.category = normalize_category(expense.category) or FALLBACK_CATEGORY
        logger.info(f"Final expense extraction: {expense.model_dump()}")
        return expense
    except Exception as e:
        logger.error(f"Final expense extraction failed: {e}")
        raise e
