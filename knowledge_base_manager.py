import os
import logging
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS  # <-- corrected import
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import GoogleGenAIEmbeddings
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.chains.llm import LLMChain 
from langchain.prompts import PromptTemplate

load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")

logger = logging.getLogger(__name__)

# Path to the pre-built FAISS index

FAISS_INDEX_PATH = "faiss_index"

def load_vectorstore():
    """Load the FAISS vector store from disk."""
    logger.info(f"Loading vector store from '{FAISS_INDEX_PATH}'...")
    if not os.path.exists(FAISS_INDEX_PATH):
        raise FileNotFoundError(
            f"FAISS index not found at '{FAISS_INDEX_PATH}'. "
            "Please run 'create_vectorstore.py' first."
        )
    embeddings = GoogleGenAIEmbeddings(model="models/embedding-001", google_api_key=google_api_key)
    vectorstore = FAISS.load_local(
        FAISS_INDEX_PATH, 
        embeddings,
        allow_dangerous_deserialization=True 
    )
    logger.info("Vector store loaded successfully.")
    return vectorstore


def get_conversation_chain(vectorstore):
    """
    Creates a RAG chain using ConversationalRetrievalChain with Gemini LLM.
    """

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.7,
        google_api_key=google_api_key
    )

    # 1. DEFINE THE RAG ANSWERING PROMPT
    # This prompt is used ONLY for the final answer, combining context, history, and the question.
    # Note: It MUST contain {context}, {chat_history}, and {question} variables.
    final_qa_template = (
        "You are a helpful and friendly game master for the card game 'Sea Salt & Paper'. "
        "Your primary role is to answer players' questions about the game rules based on the provided CONTEXT. "
        "Answer concisely and clearly. Use markdown for formatting if it helps with clarity (e.g., bullet points for lists).\n\n"
        "BEHAVIOR RULES:\n"
        "- If a user's question is about the game rules, first use the provided CONTEXT to answer.\n"
        "- If the answer cannot be found or is unclear from the provided CONTEXT, you may use reliable online sources to supplement your answer.\n"
        "- Always prioritize accuracy and consistency with the official 'Sea Salt & Paper' rules.\n"
        "- If a user asks a question that is NOT related to the game, politely state that you can only answer questions about 'Sea Salt & Paper'.\n"
        "- If the user says something conversational like 'hello', 'thanks', or 'goodbye', respond in a friendly and natural way without bringing up game rules. For example, if they say 'Thank you', you should say 'You're welcome!' or something similar.\n\n"
        "CHAT HISTORY:\n{chat_history}\n\n"
        "CONTEXT:\n{context}\n\n"
        "QUESTION: {question}\n\n"
        "ANSWER:"
    )
    
    # LangChain often performs better with this type of PromptTemplate string for RAG chains
    # than with the MessagesPlaceholder structure you used before.
    QA_PROMPT = PromptTemplate(
        template=final_qa_template, 
        input_variables=["context", "chat_history", "question"]
    )

    # 2. CREATE THE CONVERSATION MEMORY
    # ConversationalRetrievalChain needs its own memory.
    memory = ConversationBufferMemory(
        memory_key="chat_history", 
        return_messages=True,
        output_key="answer"
    )

    # 3. CONSTRUCT THE CONVERSATIONAL RETRIEVAL CHAIN
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    rag_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": QA_PROMPT}, 
        return_source_documents=True,
        output_key="answer"
    )

    return rag_chain