"""Knowledge-base operations: document files, chunk previews and Chroma rebuilds."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import tempfile
from threading import Lock
from typing import Any

from app.config import load_config
from app.logging_config import get_logger
from app.rag.loader import load_document, load_docs
from app.rag.splitter import split_docs
from app.rag.vectorstore import build_vectorstore, load_vectorstore
from app.services.errors import InvalidInputError, NotFoundError, ServiceError

logger = get_logger(__name__)

ALLOWED_UPLOAD_SUFFIXES = {".md", ".txt", ".csv", ".pdf", ".docx", ".png", ".jpg", ".jpeg"}
DOCUMENT_CATEGORIES = {"估价方法", "市场数据", "政策法规", "估价规范", "业务知识", "用户资料"}
_INDEX_LOCK = Lock()


def max_upload_bytes() -> int:
    return load_config().max_upload_bytes


def document_filename(category: str, title: str, suffix: str) -> str:
    """Build a safe ``分类_标题.ext`` filename for an uploaded document."""

    clean_title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", title).strip(" ._")
    if not clean_title:
        raise InvalidInputError("文档标题不能为空。")
    if len(clean_title) > 80:
        clean_title = clean_title[:80].rstrip()
    return f"{category}_{clean_title}{suffix}"


def document_target(source: str) -> Path:
    """Resolve a stored document name, rejecting path traversal attempts."""

    filename = Path(source).name
    docs_dir = Path(load_config().docs_dir).resolve()
    target = (docs_dir / filename).resolve()
    if target.parent != docs_dir or target.name != source or target.suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        raise InvalidInputError("非法文档来源。")
    return target


def list_documents() -> list[dict[str, Any]]:
    docs_dir = Path(load_config().docs_dir)
    documents: list[dict[str, Any]] = []
    for path in sorted(docs_dir.iterdir()) if docs_dir.exists() else []:
        if not path.is_file() or path.suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
            continue
        stat = path.stat()
        documents.append({
            "source": path.name,
            "file_type": path.suffix.lower().lstrip("."),
            "category": path.stem.split("_", 1)[0] if "_" in path.stem else "未分类",
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "size": stat.st_size,
        })
    return documents


def preview_stored_document(source: str) -> dict[str, Any]:
    target = document_target(source)
    if not target.exists():
        raise NotFoundError("文档不存在。")
    return preview_document(load_document(target))


def preview_content(content: bytes, suffix: str, source: str) -> dict[str, Any]:
    """Parse uploaded bytes in a temporary file and describe the resulting chunks."""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        document = load_document(temporary_path)
        document.metadata["source"] = source
        return preview_document(document)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def preview_document(document) -> dict[str, Any]:
    chunks = split_docs([document])
    return {
        "source": document.metadata.get("source", ""),
        "file_type": document.metadata.get("file_type", ""),
        "characters": len(document.page_content),
        "chunk_count": len(chunks),
        "overlap_ratio": 0.10,
        "chunks": [
            {
                "index": chunk.metadata["chunk"],
                "characters": chunk.metadata["chunk_size"],
                "overlap_chars": chunk.metadata["overlap_chars"],
                "text": chunk.page_content[:600],
            }
            for chunk in chunks[:12]
        ],
    }


def rebuild_index() -> int:
    """Synchronously rebuild the vector index from ``data/docs`` and return its size."""

    with _INDEX_LOCK:
        config = load_config()
        chunks = split_docs(load_docs(config.docs_dir))
        if not chunks:
            raise InvalidInputError("知识库为空，无法重建索引。")
        count = _replace_all_chunks(chunks, config.vector_db_dir)
        logger.info("vector index rebuilt: %d chunks", count)
        return count


def build_index(rebuild: bool = False) -> tuple[int, int, int]:
    """Full indexing pass used by the CLI: returns (docs, chunks, vectors)."""

    config = load_config()
    docs = load_docs(config.docs_dir)
    chunks = split_docs(docs)
    if not chunks:
        raise ServiceError("No chunks generated. Check data/docs/*.md.")

    if rebuild:
        count = _replace_all_chunks(chunks, config.vector_db_dir)
    else:
        try:
            store = load_vectorstore(config.vector_db_dir)
        except FileNotFoundError:
            store = build_vectorstore(chunks, config.vector_db_dir, rebuild=False)
        else:
            store.add_documents(chunks)
        count = len(store.get(include=[])["ids"])
    return len(docs), len(chunks), count


def _replace_all_chunks(chunks, persist_dir: str) -> int:
    """Replace every chunk in place.

    Deleting the Chroma directory would fail on Windows while the running web
    server keeps ``chroma.sqlite3`` open, therefore existing rows are deleted
    through the Chroma API instead of removing files.
    """

    try:
        store = load_vectorstore(persist_dir)
    except FileNotFoundError:
        store = build_vectorstore(chunks, persist_dir, rebuild=False)
        return len(store.get(include=[])["ids"])
    except Exception as exc:  # noqa: BLE001 - corrupt store: rebuild from scratch
        logger.warning("vector store is unreadable (%s); recreating it", exc)
        build_vectorstore(chunks, persist_dir, rebuild=True)
        store = load_vectorstore(persist_dir)
        return len(store.get(include=[])["ids"])

    existing = store.get(include=[])["ids"]
    if existing:
        store.delete(ids=existing)
    store.add_documents(chunks)
    return len(store.get(include=[])["ids"])
