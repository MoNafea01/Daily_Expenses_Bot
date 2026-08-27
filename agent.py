import logging
from typing import TypedDict, Optional, List
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

    # Memory / conversation
    conversation: List[dict]

    # Router & extraction output
    router_output: Optional[dict]

    # Persistence / verification
    appended_row: Optional[list]
    is_verified: Optional[bool]

    # Final message to send
    reply_text: Optional[str]
    success: Optional[bool]

# Node A: Load conversation history and append the new user message
def load_memory_node(state: AgentState) -> dict:
    logger.info("Starting load_memory_node")
    chat_id = state["chat_id"]
    raw_text = state["raw_text"]

    try:
        history = sheets_client.get_conversation_history(chat_id)
        conversation = list(history)
        conversation.append({"role": "user", "content": raw_text})
        logger.info(f"Loaded {len(conversation)} messages for chat {chat_id}")
        return {"conversation": conversation}
    except Exception as e:
        error_msg = f"Failed to load conversation memory: {e}"
        logger.error(error_msg)
        return {"conversation": [{"role": "user", "content": raw_text}]}

# Node B: Run the DSPy Router & Extractor
def run_router_node(state: AgentState) -> dict:
    logger.info("Starting run_router_node")
    conversation = state["conversation"]
    current_date = state["current_date"]

    try:
        output = dspy_extractor.run_router(conversation, current_date)
        return {
            "router_output": output.model_dump(),
            "success": None
        }
    except Exception as e:
        error_msg = f"Failed to classify conversation: {e}"
        logger.error(error_msg)
        return {
            "router_output": None,
            "reply_text": "Sorry, I had trouble understanding that. Please try again.",
            "success": False
        }

# Node C1: Just chatting - save history and reply with chat_response
def save_chat_node(state: AgentState) -> dict:
    logger.info("Starting save_chat_node")
    router_output = state.get("router_output") or {}
    chat_response = router_output.get("chat_response") or "I'm here to help you track your expenses!"

    conversation = list(state["conversation"])
    conversation.append({"role": "assistant", "content": chat_response})
    sheets_client.save_conversation_history(state["chat_id"], conversation)

    return {
        "conversation": conversation,
        "reply_text": chat_response,
        "success": True
    }

# Node C2: Missing fields - persist history with the prompt, send prompt
def missing_fields_node(state: AgentState) -> dict:
    logger.info("Starting missing_fields_node")
    router_output = state.get("router_output") or {}
    prompt = router_output.get("missing_fields_prompt") or "Please provide the missing expense details."

    conversation = list(state["conversation"])
    conversation.append({"role": "assistant", "content": prompt})
    sheets_client.save_conversation_history(state["chat_id"], conversation)

    return {
        "conversation": conversation,
        "reply_text": prompt,
        "success": True
    }

# Node D: Persist expense, verify, clear memory
def _description_from_conversation(conversation: list) -> str:
    """Builds a compact raw-text summary of the user's messages for the sheet."""
    user_msgs = [m["content"] for m in conversation if m.get("role") == "user"]
    return " | ".join(user_msgs)

def persist_expense_node(state: AgentState) -> dict:
    logger.info("Starting persist_expense_node")
    chat_id = state["chat_id"]
    conversation = state.get("conversation") or []
    current_date = state.get("current_date")

    # Run a dedicated complete extraction over the FULL conversation so that
    # fields mentioned in earlier turns (e.g. description/category) are not lost
    # when the final message only provides the date or amount.
    try:
        final_expense = dspy_extractor.extract_final_expense(conversation, current_date)
        expense = final_expense.model_dump()
    except Exception as e:
        error_msg = f"Failed to extract complete expense details: {e}"
        logger.error(error_msg)
        return {
            "appended_row": None,
            "is_verified": False,
            "reply_text": f"❌ *Transaction failed*\n\nUnable to process the expense. Error:\n`{error_msg}`",
            "success": False
        }

    raw_text = _description_from_conversation(conversation)

    try:
        row = sheets_client.append_expense(expense, raw_text)
        logger.info(f"Appended expense row: {row}")

        verified = sheets_client.verify_expense_write(row)
        if not verified:
            raise ValueError("Google Sheets write verification failed. The last row does not match the expected row.")

        # Clear conversation memory since the expense was recorded
        sheets_client.clear_conversation_history(chat_id)

        # Build confirmation message
        date = expense.get("date") or "Unknown"
        amount = expense.get("amount") or 0
        currency = expense.get("currency") or "EGP"
        description = expense.get("description") or "Unspecified"
        category = expense.get("category") or "Other"
        payment = expense.get("payment_method") or "Cash"

        message = (
            f"✅ *Expense Logged Successfully!*\n\n"
            f"📅 *Date:* {date}\n"
            f"💰 *Amount:* {amount} {currency}\n"
            f"📝 *Description:* {description}\n"
            f"🏷️ *Category:* {category}\n"
            f"💳 *Payment Method:* {payment}\n\n"
            f"_Double-checked and verified in Google Sheets!_"
        )

        return {
            "appended_row": row,
            "is_verified": True,
            "reply_text": message,
            "success": True
        }
    except Exception as e:
        error_msg = f"Failed to persist expense: {e}"
        logger.error(error_msg)
        return {
            "appended_row": None,
            "is_verified": False,
            "reply_text": f"❌ *Transaction failed*\n\nUnable to process the expense. Error:\n`{error_msg}`",
            "success": False
        }

# Node E: Send the final reply to Telegram
def respond_node(state: AgentState) -> dict:
    logger.info("Starting respond_node")
    chat_id = state["chat_id"]
    reply_text = state.get("reply_text") or ""
    telegram_utils.send_telegram_message(chat_id, reply_text)
    return {}

# Router branch after DSPy run
def route_after_router(state: AgentState):
    if state.get("success") is False:
        return "respond_no_reply"
    router_output = state.get("router_output") or {}
    if not router_output.get("is_expense_log"):
        return "save_chat"
    missing = router_output.get("missing_fields_prompt")
    if missing:
        return "missing_fields"
    return "persist"

# Build LangGraph workflow
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("load_memory", load_memory_node)
workflow.add_node("run_router", run_router_node)
workflow.add_node("save_chat", save_chat_node)
workflow.add_node("missing_fields", missing_fields_node)
workflow.add_node("persist", persist_expense_node)
workflow.add_node("respond", respond_node)

# Set entry point
workflow.set_entry_point("load_memory")

# Add edges
workflow.add_edge("load_memory", "run_router")

workflow.add_conditional_edges(
    "run_router",
    route_after_router,
    {
        "save_chat": "save_chat",
        "missing_fields": "missing_fields",
        "persist": "persist",
        "respond_no_reply": "respond"
    }
)

workflow.add_edge("save_chat", "respond")
workflow.add_edge("missing_fields", "respond")
workflow.add_edge("persist", "respond")
workflow.add_edge("respond", END)

# Compile graph
expense_agent = workflow.compile()


def run_expense_flow(raw_text: str, chat_id: int, current_date: str = None) -> dict:
    """
    Executes the entire conversational LangGraph workflow for a user message.
    Loads persistent memory, routes, collects missing fields across turns,
    records verified expenses, and clears memory on completion.
    """
    from datetime import datetime as _dt
    if not current_date:
        current_date = _dt.now().strftime("%Y-%m-%d")

    initial_state = {
        "raw_text": raw_text,
        "chat_id": chat_id,
        "current_date": current_date,
        "conversation": [],
        "router_output": None,
        "appended_row": None,
        "is_verified": None,
        "reply_text": None,
        "success": None,
    }

    logger.info(f"Triggering conversational LangGraph workflow for chat {chat_id}")
    return expense_agent.invoke(initial_state)
