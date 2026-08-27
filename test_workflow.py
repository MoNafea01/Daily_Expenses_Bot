import sys
import logging
from datetime import datetime
import config
import dspy_extractor
import sheets_client
import agent

# Configure logging to stdout
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass # python 2 or older versions without reconfigure

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("test_workflow")


def run_tests():
    logger.info("=== STARTING WORKFLOW VERIFICATION (Conversational) ===")

    current_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Using current date anchor: {current_date}")

    # ------------------------------------------------------------------
    # Test 1: Just chatting (e.g. "Hello bot").
    # Expect: is_expense_log = False and a chat response.
    # ------------------------------------------------------------------
    logger.info("\n--- Test 1: Chatting (no expense) ---")
    try:
        res = dspy_extractor.run_router(
            [{"role": "user", "content": "Hello bot, how are you?"}],
            current_date
        )
        logger.info(f"is_expense_log={res.is_expense_log}, chat_response='{res.chat_response}'")
        if res.is_expense_log:
            logger.error("Test 1 FAILED: expected is_expense_log=False")
        else:
            logger.info("Test 1 PASSED: bot responded to casual chat.")
    except Exception as e:
        logger.error(f"Test 1 failed with exception: {e}")

    # ------------------------------------------------------------------
    # Test 2: Incomplete expense (e.g. "I ate Kabab").
    # Expect: is_expense_log = True and a prompt for the missing amount.
    # ------------------------------------------------------------------
    logger.info("\n--- Test 2: Incomplete expense (missing amount) ---")
    try:
        res = dspy_extractor.run_router(
            [{"role": "user", "content": "I ate kabab"}],
            current_date
        )
        logger.info(f"is_expense_log={res.is_expense_log}, missing_fields_prompt='{res.missing_fields_prompt}'")
        logger.info(f"category={res.category}, description={res.description}")
        if not res.is_expense_log:
            logger.error("Test 2 FAILED: expected is_expense_log=True")
        elif not res.missing_fields_prompt:
            logger.error("Test 2 FAILED: expected a missing fields prompt (amount missing)")
        else:
            logger.info("Test 2 PASSED: bot prompted for missing amount.")
    except Exception as e:
        logger.error(f"Test 2 failed with exception: {e}")

    # ------------------------------------------------------------------
    # Test 3: Complete turn (History: "I ate Kabab" + Bot prompt + "It cost 150").
    # Expect: full details resolved (Amount: 150, category food, desc kabab, date today)
    # and no missing fields prompt.
    # ------------------------------------------------------------------
    logger.info("\n--- Test 3: Complete expense across turns ---")
    conversation = [
        {"role": "user", "content": "I ate kabab"},
        {"role": "assistant", "content": "How much did it cost?"},
        {"role": "user", "content": "It cost 150"},
    ]
    try:
        res = dspy_extractor.run_router(conversation, current_date)
        logger.info(
            f"is_expense_log={res.is_expense_log}, amount={res.amount}, category={res.category}, "
            f"description={res.description}, date={res.date}, missing='{res.missing_fields_prompt}'"
        )
        if not res.is_expense_log:
            logger.error("Test 3 FAILED: expected is_expense_log=True")
        elif res.missing_fields_prompt:
            logger.error("Test 3 FAILED: expected no missing fields prompt")
        elif res.amount is None or float(res.amount) != 150.0:
            logger.error(f"Test 3 FAILED: unexpected amount {res.amount}")
        else:
            logger.info("Test 3 PASSED: full expense resolved with no missing fields.")
    except Exception as e:
        logger.error(f"Test 3 failed with exception: {e}")

    # ------------------------------------------------------------------
    # Test 4: Full conversational LangGraph flow (mocked Telegram send)
    # Simulates an incomplete message first, then completes it across turns,
    # verifying memory persistence and final recording.
    # ------------------------------------------------------------------
    logger.info("\n--- Test 4: Full LangGraph conversational flow (Mocked Telegram Send) ---")
    import telegram_utils
    original_send = telegram_utils.send_telegram_message

    def mock_send(chat_id, text, parse_mode="Markdown"):
        logger.info(f"MOCK TELEGRAM SEND to chat {chat_id}:")
        print("--------------------")
        print(text)
        print("--------------------")
        return True

    telegram_utils.send_telegram_message = mock_send

    test_chat = 999998
    try:
        # Clear any prior memory for this test chat so the flow starts fresh.
        sheets_client.clear_conversation_history(test_chat)

        logger.info("Turn 1: incomplete expense...")
        r1 = agent.run_expense_flow(
            raw_text="سيارة اجرة اليوم",
            chat_id=test_chat,
            current_date=current_date
        )
        logger.info(f"Turn 1 reply: {r1.get('reply_text')}")
        logger.info(f"Turn 1 success: {r1.get('success')}, persisted={r1.get('appended_row') is not None}")

        logger.info("Turn 2: completing the expense...")
        r2 = agent.run_expense_flow(
            raw_text="كانت 120",
            chat_id=test_chat,
            current_date=current_date
        )
        logger.info(f"Turn 2 reply: {r2.get('reply_text')}")
        logger.info(f"Turn 2 success: {r2.get('success')}, is_verified={r2.get('is_verified')}")

        history_after = sheets_client.get_conversation_history(test_chat)
        logger.info(f"Memory after completion (should be cleared/empty): {history_after}")
    except Exception as e:
        logger.error(f"Test 4 failed with exception: {e}")
    finally:
        telegram_utils.send_telegram_message = original_send

    logger.info("\n=== WORKFLOW VERIFICATION COMPLETED ===")


if __name__ == "__main__":
    run_tests()
