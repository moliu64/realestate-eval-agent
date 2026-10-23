from __future__ import annotations

import shutil
from pathlib import Path
import threading

from langchain_core.documents import Document

from app.embeddings import get_embeddings
from app.logging_config import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "realestate_eval_docs"
COLLECTION_METADATA = {"hnsw:space": "cosine"}

_SIGNATURE_LOCK = threading.Lock()
_LAST_SIGNATURE: float | None = None


def build_vectorstore(
    docs: list[Document],
    persist_dir: str,
    rebuild: bool = False,
):
    from langchain_chroma import Chroma

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


def load_vectorstore(persist_dir: str):
    """Open the persisted collection, detecting out-of-process index changes.

    Chroma caches its system client per process, so after ``python run.py index``
    rewrites the database the long-running web process would otherwise keep
    serving a stale HNSW segment. The directory signature is compared on every
    access and Chroma's shared cache is dropped when it changed.
    """

    from langchain_chroma import Chroma

    path = Path(persist_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Vector database not found: {path}. Run `python run.py index` first."
        )
    _invalidate_chroma_cache_if_changed(path)
    return Chroma(
        persist_directory=str(path),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
        collection_metadata=COLLECTION_METADATA,
    )


def _invalidate_chroma_cache_if_changed(path: Path) -> None:
    global _LAST_SIGNATURE
    signature = _directory_signature(path)
    with _SIGNATURE_LOCK:
        if _LAST_SIGNATURE is not None and signature != _LAST_SIGNATURE:
            try:
                from chromadb.api.client import SharedSystemClient

                SharedSystemClient.clear_system_cache()
                logger.info("vector index changed on disk; Chroma client cache cleared")
            except Exception:  # noqa: BLE001 - cache clearing is best effort
                logger.warning("failed to clear Chroma client cache", exc_info=True)
        _LAST_SIGNATURE = signature


def _directory_signature(path: Path) -> float:
    latest = 0.0
    try:
        for entry in path.rglob("*"):
            try:
                latest = max(latest, entry.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        return 0.0
    return latest
