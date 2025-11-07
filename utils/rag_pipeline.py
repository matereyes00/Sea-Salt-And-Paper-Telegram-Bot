import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

class RAGPipeline:
    """A simple RAG pipeline using Google Gemini model for your Telegram bot."""

    def __init__(self):
        logger.info("Initializing RAG pipeline with Gemini model...")
        self.model = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0.7,
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
        logger.info("✅ RAG pipeline initialized successfully.")

    def get_conversation_chain(self):
        """
        Returns the model instance that can be used for conversation
        (compatible with your ainvoke usage in telegram_handlers).
        """
        return self.model

# Instantiate the pipeline at the module level

rag_pipeline = RAGPipeline()
