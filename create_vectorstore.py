import logging
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from games.sea_salt_and_paper import RULES_TEXT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the folder where the index will be saved
FAISS_INDEX_PATH = "faiss_index"

def create_and_save_knowledge_base():
    """
    Creates the vector store from the game rules and saves it to disk.
    """
    logger.info("Setting up knowledge base for the selected game...")

    # 1. Split the rules text into manageable chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = splitter.split_text(RULES_TEXT)
    docs = [Document(page_content=chunk) for chunk in chunks]
    logger.info(f"Split rules into {len(docs)} documents.")

    # 2. Initialize the embeddings model (this will download it)
    logger.info("Loading sentence-transformer model. This may take a moment...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # 3. Create the FAISS vector store from the documents and embeddings
    logger.info("Creating FAISS vector store...")
    vectorstore = FAISS.from_documents(docs, embeddings)

    # 4. Save the vector store to a local folder
    vectorstore.save_local(FAISS_INDEX_PATH)
    logger.info(f"Knowledge base created and saved to '{FAISS_INDEX_PATH}'.")
    logger.info("You can now commit this folder to your repository.")

if __name__ == "__main__":
    create_and_save_knowledge_base()
