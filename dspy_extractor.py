import logging
from datetime import datetime
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

# Define the Pydantic model for structured output
class ExpenseExtraction(BaseModel):
    date: str = Field(
        description="ISO 8601 formatted date (YYYY-MM-DD) when the expense occurred. Resolve relative dates (e.g. 'today', 'yesterday', 'last Wednesday') using the provided current_date as the reference anchor."
    )
    amount: float = Field(
        description="The numerical amount of the expense (e.g. 150.0). Always output a positive number."
    )
    currency: str = Field(
        description="The currency code (e.g. EGP, USD, EUR). Default to 'EGP' if no currency is mentioned and no other currency is inferred."
    )
    description: str = Field(
        description="A concise description of what was purchased (e.g. 'Uber to work', 'McDonalds meal'). Do not include the amount or date in this description."
    )
    category: str = Field(
        description="The category of the expense. Must be one of: Food, Transport, Utilities, Entertainment, Health, Shopping, Education, Other."
    )
    payment_method: str = Field(
        description="The payment method or account used. Must be one of: Cash, Card, Wallet, Instapay, Bank, Other. Default to 'Cash' if not specified."
    )

# Define the DSPy Signature
class ExpenseSignature(dspy.Signature):
    """
    Parse an expense transaction message.
    Extract the transaction details such as date, amount, currency, description, category, and payment method.
    Resolve relative dates like 'today', 'yesterday', or 'last Friday' relative to the provided current_date (YYYY-MM-DD).
    """
    text: str = dspy.InputField(desc="The raw text message describing the expense.")
    current_date: str = dspy.InputField(desc="The current date in YYYY-MM-DD format, used as the anchor for resolving relative dates.")
    extracted_expense: ExpenseExtraction = dspy.OutputField(desc="Structured expense data.")

def parse_expense_text(text: str, current_date_str: str = None) -> ExpenseExtraction:
    """
    Uses DSPy Predict to parse the input text and extract an ExpenseExtraction object.
    """
    if not current_date_str:
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        
    predictor = dspy.Predict(ExpenseSignature)
    
    try:
        logger.info(f"Parsing expense text: '{text}' relative to current date '{current_date_str}'")
        result = predictor(text=text, current_date=current_date_str)
        logger.info(f"DSPy parsing successful: {result.extracted_expense}")
        return result.extracted_expense
    except Exception as e:
        logger.error(f"DSPy parsing failed: {e}")
        raise e
