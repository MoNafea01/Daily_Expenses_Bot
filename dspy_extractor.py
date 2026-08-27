import logging
import json
from datetime import datetime
from typing import Optional, List
import dspy
from pydantic import BaseModel, Field
import config

logger = logging.getLogger(__name__)

# Initialize DSPy language model using Groq through LiteLLM
try:
    # Use gpt-oss-20b model from Groq
    lm = dspy.LM("groq/openai/gpt-oss-20b", api_key=config.GROQ_API_KEY)
    dspy.configure(lm=lm)
    logger.info("Configured DSPy with Groq LM (openai/gpt-oss-20b)")
except Exception as e:
    logger.error(f"Error configuring DSPy LM: {e}")
    raise

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
        description="Expense category in Arabic/English (e.g. اكل/Food, مواصلات/Transport, فواتير/Utilities, تسوق/Shopping, ترفيه/Entertainment, صحة/Health, أخرى/Other)."
    )
    description: Optional[str] = Field(description="Description of purchase.")
    currency: Optional[str] = Field(description="Currency. Default is EGP.")
    payment_method: Optional[str] = Field(description="Payment method. Default is Cash.")

    # Missing Fields Prompt
    missing_fields_prompt: Optional[str] = Field(
        description="If is_expense_log is True but any of the mandatory fields (date, amount, category) are missing, generate a friendly, natural message in the user's language (Arabic or English) asking for the missing fields. If all mandatory fields are present, leave this empty."
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
    category: str = Field(description="The expense category. Must be one of: Food, Transport, Utilities, Entertainment, Health, Shopping, Education, Other (or Arabic equivalents).")
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

# Map canonical English categories to support Arabic names too
CATEGORY_ALIASES = {
    "اكل": "Food",
    "طعام": "Food",
    "food": "Food",
    "مواصلات": "Transport",
    "transport": "Transport",
    "فواتير": "Utilities",
    "utilities": "Utilities",
    "تسوق": "Shopping",
    "shopping": "Shopping",
    "ترفيه": "Entertainment",
    "entertainment": "Entertainment",
    "صحة": "Health",
    "health": "Health",
    "تعليم": "Education",
    "education": "Education",
    "أخرى": "Other",
    "other": "Other"
}

def normalize_category(category: Optional[str]) -> Optional[str]:
    """Maps an Arabic/English category alias to the canonical English category."""
    if not category:
        return None
    key = category.strip().lower()
    # Handle case where category is a combined string like "اكل/Food"
    if "/" in key:
        key = key.split("/")[0].strip()
    return CATEGORY_ALIASES.get(key, category.strip())

def run_router(conversation: list, current_date_str: str = None) -> RouterOutput:
    """
    Uses DSPy Predict to classify the conversation and extract expense fields
    (or generate a chat response) based on the full conversation history.
    """
    if not current_date_str:
        current_date_str = datetime.now().strftime("%Y-%m-%d")

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
    if not current_date_str:
        current_date_str = datetime.now().strftime("%Y-%m-%d")

    conversation_str = json.dumps(conversation, ensure_ascii=False)
    predictor = dspy.Predict(FinalExpenseSignature)

    try:
        logger.info(f"Extracting final expense from {len(conversation)} messages relative to date '{current_date_str}'")
        result = predictor(conversation=conversation_str, current_date=current_date_str)
        expense = result.expense
        expense.category = normalize_category(expense.category) or expense.category
        logger.info(f"Final expense extraction: {expense.model_dump()}")
        return expense
    except Exception as e:
        logger.error(f"Final expense extraction failed: {e}")
        raise e
