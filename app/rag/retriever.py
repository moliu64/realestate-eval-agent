from langchain_core.documents import Document

from app.config import load_config
from app.rag.vectorstore import load_vectorstore


def retrieve(query: str, k: int = 4) -> list[tuple[Document, float]]:
    config = load_config()
    vectorstore = load_vectorstore(config.vector_db_dir)
    return vectorstore.similarity_search_with_relevance_scores(query, k=k)
