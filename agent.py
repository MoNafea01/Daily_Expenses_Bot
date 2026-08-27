import logging
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
import dspy_extractor
import sheets_client
import telegram_utils

logger = logging.getLogger(__name__)

# Define state structure for LangGraph
class AgentState(TypedDict):
    # Inputs
    raw_text: str
    chat_id: int
    current_date: str
    
    # Intermediate outputs
    extracted_expense: Optional[dict]
    appended_row: Optional[list]
    
    # Verification/Final state
    is_verified: Optional[bool]
    error_message: Optional[str]

# Define Node 1: Parse the expense text
def parse_expense_node(state: AgentState) -> dict:
    logger.info("Starting parse_expense_node")
    raw_text = state["raw_text"]
    current_date = state["current_date"]
    
    try:
        extraction = dspy_extractor.parse_expense_text(raw_text, current_date)
        # Convert pydantic model to dict
        extraction_dict = extraction.model_dump()
        return {
            "extracted_expense": extraction_dict,
            "error_message": None
        }
    except Exception as e:
        error_msg = f"Failed to parse transaction text: {e}"
        logger.error(error_msg)
        return {
            "error_message": error_msg
        }

# Define Node 2: Persist to Sheets
def persist_expense_node(state: AgentState) -> dict:
    logger.info("Starting persist_expense_node")
    if state.get("error_message"):
        # Skip if there's an error from previous node
        return {}
        
    extracted_expense = state["extracted_expense"]
    raw_text = state["raw_text"]
    
    try:
        row = sheets_client.append_expense(extracted_expense, raw_text)
        return {
            "appended_row": row,
            "error_message": None
        }
    except Exception as e:
        error_msg = f"Failed to persist to Google Sheets: {e}"
        logger.error(error_msg)
        return {
            "error_message": error_msg
        }

# Define Node 3: Verify the write
def verify_write_node(state: AgentState) -> dict:
    logger.info("Starting verify_write_node")
    if state.get("error_message"):
        return {"is_verified": False}
        
    appended_row = state["appended_row"]
    
    try:
        is_verified = sheets_client.verify_expense_write(appended_row)
        if is_verified:
            logger.info("Successfully verified Google Sheet write.")
            return {"is_verified": True}
        else:
            error_msg = "Google Sheets write verification failed. The last row does not match the expected row."
            logger.error(error_msg)
            return {
                "is_verified": False,
                "error_message": error_msg
            }
    except Exception as e:
        error_msg = f"Exception during write verification: {e}"
        logger.error(error_msg)
        return {
            "is_verified": False,
            "error_message": error_msg
        }

# Define Node 4: Send telegram response
def respond_node(state: AgentState) -> dict:
    logger.info("Starting respond_node")
    chat_id = state["chat_id"]
    error_message = state.get("error_message")
    extracted = state.get("extracted_expense")
    
    if error_message:
        message = (
            f"❌ *Transaction failed*\n\n"
            f"Unable to process transaction. Error:\n`{error_message}`"
        )
    else:
        # Formulate beautiful markdown confirmation message
        message = (
            f"✅ *Expense Logged Successfully!*\n\n"
            f"📅 *Date:* {extracted.get('date')}\n"
            f"💰 *Amount:* {extracted.get('amount')} {extracted.get('currency')}\n"
            f"📝 *Description:* {extracted.get('description')}\n"
            f"🏷️ *Category:* {extracted.get('category')}\n"
            f"💳 *Payment Method:* {extracted.get('payment_method')}\n\n"
            f"_Double-checked and verified in Google Sheets!_"
        )
        
    telegram_utils.send_telegram_message(chat_id, message)
    return {}

# Define router / conditional edge
def route_after_parse(state: AgentState):
    if state.get("error_message"):
        # Skip persistence and verification, go straight to respond
        return "respond"
    return "persist"

def route_after_persist(state: AgentState):
    if state.get("error_message"):
        return "respond"
    return "verify"

# Build LangGraph workflow
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("parse", parse_expense_node)
workflow.add_node("persist", persist_expense_node)
workflow.add_node("verify", verify_write_node)
workflow.add_node("respond", respond_node)

# Set entry point
workflow.set_entry_point("parse")

# Add edges
workflow.add_conditional_edges(
    "parse",
    route_after_parse,
    {
        "persist": "persist",
        "respond": "respond"
    }
)
workflow.add_conditional_edges(
    "persist",
    route_after_persist,
    {
        "verify": "verify",
        "respond": "respond"
    }
)
workflow.add_edge("verify", "respond")
workflow.add_edge("respond", END)

# Compile graph
expense_agent = workflow.compile()

def run_expense_flow(raw_text: str, chat_id: int, current_date: str = None) -> dict:
    """
    Executes the entire LangGraph workflow for an expense text.
    """
    initial_state = {
        "raw_text": raw_text,
        "chat_id": chat_id,
        "current_date": current_date or "",
        "extracted_expense": None,
        "appended_row": None,
        "is_verified": None,
        "error_message": None
    }
    
    logger.info(f"Triggering LangGraph workflow for raw text: '{raw_text}'")
    return expense_agent.invoke(initial_state)
