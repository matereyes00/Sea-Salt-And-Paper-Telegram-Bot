import os
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")

logger = logging.getLogger(__name__)

# Define the path to the pre-built index
FAISS_INDEX_PATH = "faiss_index"

def load_vectorstore():
    """Loads the pre-built FAISS vector store from the local disk."""
    logger.info(f"Loading vector store from '{FAISS_INDEX_PATH}'...")
    if not os.path.exists(FAISS_INDEX_PATH):
        raise FileNotFoundError(
            f"FAISS index not found at '{FAISS_INDEX_PATH}'. "
            "Please run 'create_vectorstore.py' first to generate it."
        )
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vectorstore = FAISS.load_local(
        FAISS_INDEX_PATH,
        embeddings,
        allow_dangerous_deserialization=True
    )
    logger.info("Vector store loaded successfully.")
    return vectorstore

def get_conversation_chain(vectorstore):
    """
    Creates a sophisticated, history-aware conversational retrieval chain.
    """
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.7,
        google_api_key=google_api_key
    )

    # This is the core instruction that defines the bot's personality and behavior.
    system_prompt_template = (
            "You are a helpful and friendly game master for the card game 'Sea Salt & Paper'. "
            "Your primary role is to answer players' questions about the game rules based on the provided context. "
            "Answer concisely and clearly. Use markdown for formatting if it helps with clarity (e.g., bullet points for lists).\n\n"
            "BEHAVIOR RULES:\n"
            "- If a user's question is about the game rules, first use the provided context to answer.\n"
            "- If the answer cannot be found or is unclear from the provided context, you may use reliable online sources to supplement your answer.\n"
            "- Always prioritize accuracy and consistency with the official 'Sea Salt & Paper' rules.\n"
            "- If a user asks a question that is NOT related to the game, politely state that you can only answer questions about 'Sea Salt & Paper'.\n"
            "- If the user says something conversational like 'hello', 'thanks', or 'goodbye', respond in a friendly and natural way without bringing up game rules. For example, if they say 'Thank you', you should say 'You're welcome!' or something similar.\n\n"
            "CONTEXT:\n{context}"
        )


    # This prompt is used by the main chain to generate the final answer.
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt_template),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    
    # This chain takes the user's question and the document context and generates an answer.
    question_answer_chain = create_stuff_documents_chain(llm, prompt)

    # This prompt helps the AI generate a better search query based on conversation history.
    retriever_prompt = ChatPromptTemplate.from_messages([
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        ("human", "Given the above conversation, generate a search query to look up information relevant to the conversation.")
    ])

    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    
    # This chain rephrases the user's question to be a better standalone search query.
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, retriever_prompt
    )
    
    # This is the final chain that ties everything together.
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    return rag_chain