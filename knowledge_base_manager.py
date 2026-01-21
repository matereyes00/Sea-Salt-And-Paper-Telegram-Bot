import os
import time
import logging
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate

# ------------------------------------------------------------------
# ENV & LOGGING
# ------------------------------------------------------------------

load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------------

FAISS_INDEX_PATH = "faiss_index"
MIN_SECONDS_BETWEEN_EMBEDS = 2.5

# ------------------------------------------------------------------
# GLOBAL EMBEDDINGS (CRITICAL FIX)
# ------------------------------------------------------------------

EMBEDDINGS = GoogleGenerativeAIEmbeddings(
    model="models/embedding-001",
    google_api_key=google_api_key
)

# ------------------------------------------------------------------
# RATE LIMITER
# ------------------------------------------------------------------

_last_embed_time = 0.0

def _rate_limit():
    global _last_embed_time
    now = time.time()
    elapsed = now - _last_embed_time
    if elapsed < MIN_SECONDS_BETWEEN_EMBEDS:
        time.sleep(MIN_SECONDS_BETWEEN_EMBEDS - elapsed)
    _last_embed_time = time.time()

# ------------------------------------------------------------------
# VECTORSTORE LOADING
# ------------------------------------------------------------------

def load_vectorstore():
    """Load the FAISS vector store from disk."""
    logger.info(f"Loading vector store from '{FAISS_INDEX_PATH}'...")

    if not os.path.exists(FAISS_INDEX_PATH):
        raise FileNotFoundError(
            f"FAISS index not found at '{FAISS_INDEX_PATH}'. "
            "Please run 'create_vectorstore.py' first."
        )

    vectorstore = FAISS.load_local(
        FAISS_INDEX_PATH,
        EMBEDDINGS,
        allow_dangerous_deserialization=True
    )

    logger.info("Vector store loaded successfully.")
    return vectorstore

# ------------------------------------------------------------------
# INPUT ROUTING (SKIP RAG FOR CASUAL CHAT)
# ------------------------------------------------------------------

def should_use_rag(user_input: str) -> bool:
    casual_phrases = [
        "hi", "hello", "hey",
        "thanks", "thank you",
        "bye", "goodbye"
    ]
    text = user_input.lower().strip()
    return not any(p in text for p in casual_phrases)

# ------------------------------------------------------------------
# CONVERSATION CHAIN
# ------------------------------------------------------------------

def get_conversation_chain(vectorstore):
    """Creates a RAG chain using ConversationalRetrievalChain with Gemini."""

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.7,
        google_api_key=google_api_key
    )

    final_qa_template = (
        "You are a helpful and friendly game master for the card game 'Sea Salt & Paper'. "
        "Your primary role is to answer players' questions about the game rules based on the provided CONTEXT. "
        "Answer concisely and clearly. Use markdown for formatting if it helps with clarity.\n\n"
        "BEHAVIOR RULES:\n"
        "- If a user's question is about the game rules, first use the provided CONTEXT to answer.\n"
        "- If the answer cannot be found or is unclear from the provided CONTEXT, you may use reliable online sources.\n"
        "- Always prioritize accuracy with the official 'Sea Salt & Paper' rules.\n"
        "- If a question is NOT related to the game, politely state that you can only answer questions about the game.\n"
        "- If the user is conversational (hello, thanks, goodbye), respond naturally.\n\n"
        "CHAT HISTORY:\n{chat_history}\n\n"
        "CONTEXT:\n{context}\n\n"
        "QUESTION: {question}\n\n"
        "ANSWER:"
    )

    QA_PROMPT = PromptTemplate(
        template=final_qa_template,
        input_variables=["context", "chat_history", "question"]
    )

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer"
    )

    retriever = vectorstore.as_retriever(
        search_kwargs={"k": 2}  # reduced from 3
    )

    rag_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": QA_PROMPT},
        return_source_documents=True,
        output_key="answer"
    )

    return rag_chain, llm

# ------------------------------------------------------------------
# SAFE INVOKE WRAPPER
# ------------------------------------------------------------------

def invoke_safely(rag_chain, llm, user_input: str):
    """
    Routes input either to RAG (with rate limiting)
    or directly to the LLM for casual chat.
    """

    if should_use_rag(user_input):
        _rate_limit()
        result = rag_chain.invoke({"question": user_input})
        return result["answer"]
    else:
        return llm.invoke(user_input).content
