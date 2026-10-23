from langchain_core.documents import Document

from app.config import load_config
from app.rag.vectorstore import load_vectorstore


def retrieve(query: str, k: int = 4) -> list[tuple[Document, float]]:
    config = load_config()
    vectorstore = load_vectorstore(config.vector_db_dir)
    if not vectorstore.get(include=[])["ids"]:
        raise RuntimeError(
            "向量库为空，请先运行 `python run.py index` 构建索引。"
        )
    return vectorstore.similarity_search_with_relevance_scores(query, k=k)
