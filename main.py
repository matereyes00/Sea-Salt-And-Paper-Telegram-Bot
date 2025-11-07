import os
import logging
from knowledge_base_manager import load_vectorstore
from telegram_handlers import setup_telegram_bot
from dotenv import load_dotenv # type: ignore

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def main():
    """Initializes and runs the bot."""
    # Get environment variables
    # Railway provides the PORT variable automatically.
    port = int(os.environ.get('PORT', '8080'))
    # You need to set WEBHOOK_URL in your Railway variables.
    webhook_url = os.getenv("WEBHOOK_URL")
    
    if not webhook_url:
        logger.error("WEBHOOK_URL environment variable not set!")
        return

    logger.info("Loading knowledge base from disk...")
    # Load the pre-built vectorstore from the 'faiss_index' folder
    vectorstore = load_vectorstore()
    logger.info("Knowledge base is ready.")

    logger.info(f"Starting bot on port {port} with webhook URL: {webhook_url}")
    # Pass the vectorstore, port, and webhook URL to the bot setup
    setup_telegram_bot(vectorstore, port, webhook_url)

if __name__ == "__main__":
    main()

