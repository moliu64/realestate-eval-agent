from pathlib import Path
from functools import lru_cache
import shutil

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.embeddings import get_embeddings

COLLECTION_NAME = "realestate_eval_docs"
COLLECTION_METADATA = {"hnsw:space": "cosine"}


def build_vectorstore(
    docs: list[Document],
    persist_dir: str,
    rebuild: bool = False,
) -> Chroma:
    path = Path(persist_dir)
    if rebuild and path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)

    return Chroma.from_documents(
        documents=docs,
        embedding=get_embeddings(),
        persist_directory=str(path),
        collection_name=COLLECTION_NAME,
        collection_metadata=COLLECTION_METADATA,
    )


@lru_cache(maxsize=1)
def load_vectorstore(persist_dir: str) -> Chroma:
    path = Path(persist_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Vector database not found: {path}. Run `python scripts/build_index.py --rebuild` first."
        )
    return Chroma(
        persist_directory=str(path),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
        collection_metadata=COLLECTION_METADATA,
    )
