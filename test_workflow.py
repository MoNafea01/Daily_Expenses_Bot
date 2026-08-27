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
    logger.info("=== STARTING WORKFLOW VERIFICATION ===")
    
    # 1. Test DSPy parsing
    test_texts = [
        "bought groceries at Carrefour for 350 EGP yesterday using card",
        "spent 12.5 USD on Uber ride today",
        "paid rent 5000 EGP cash"
    ]
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Using current date anchor: {current_date}")
    
    parsed_results = []
    for idx, text in enumerate(test_texts, 1):
        logger.info(f"\n--- Test {idx}: Parsing Text: '{text}' ---")
        try:
            res = dspy_extractor.parse_expense_text(text, current_date)
            logger.info(f"Result {idx}: date={res.date}, amount={res.amount}, currency={res.currency}, description='{res.description}', category={res.category}, payment_method={res.payment_method}")
            parsed_results.append(res.model_dump())
        except Exception as e:
            logger.error(f"Failed parsing test {idx}: {e}")
            return
            
    # 2. Test Google Sheets client with the first parsed result
    if not parsed_results:
        logger.error("No parsed results to test sheets with.")
        return
        
    logger.info("\n--- Test Google Sheets Append & Verify ---")
    test_expense = parsed_results[0]
    raw_text = test_texts[0]
    
    try:
        # Check sheet connection by getting last record
        logger.info("Connecting to Google Sheets...")
        last_rec_before = sheets_client.get_last_record()
        logger.info(f"Last record in sheet before write: {last_rec_before}")
        
        # Append mock record
        logger.info(f"Appending row: {test_expense}")
        appended_row = sheets_client.append_expense(test_expense, raw_text)
        logger.info(f"Appended row values: {appended_row}")
        
        # Verify the append
        logger.info("Verifying write...")
        is_verified = sheets_client.verify_expense_write(appended_row)
        if is_verified:
            logger.info("✅ Verification PASSED: Last written row matches what we sent!")
        else:
            logger.error("❌ Verification FAILED: Last written row does not match what we sent!")
            
    except Exception as e:
        logger.error(f"Google Sheets test failed: {e}")
        return

    # 3. Test the full LangGraph agent flow (without sending actual telegram message by mocking sending)
    logger.info("\n--- Test Full LangGraph Flow (Mocked Telegram Send) ---")
    
    # Mock send_telegram_message to verify the flow is executed end-to-end
    import telegram_utils
    original_send = telegram_utils.send_telegram_message
    
    def mock_send(chat_id, text, parse_mode="Markdown"):
        logger.info(f"MOCK TELEGRAM SEND to chat {chat_id}:")
        print("--------------------")
        print(text)
        print("--------------------")
        return True
        
    telegram_utils.send_telegram_message = mock_send
    
    try:
        logger.info("Invoking Agent Flow...")
        result = agent.run_expense_flow(
            raw_text="spent 45 EGP on cigarettes cash",
            chat_id=999999,
            current_date=current_date
        )
        logger.info(f"Agent flow finished. Final state keys: {list(result.keys())}")
        logger.info(f"Final state: is_verified={result.get('is_verified')}, error_message={result.get('error_message')}")
    except Exception as e:
        logger.error(f"LangGraph Agent test failed: {e}")
    finally:
        # Restore original function
        telegram_utils.send_telegram_message = original_send

    logger.info("\n=== WORKFLOW VERIFICATION COMPLETED ===")

if __name__ == "__main__":
    run_tests()
