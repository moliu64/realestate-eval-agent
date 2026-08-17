from langchain_core.documents import Document

CHUNK_SIZE = 500
CHUNK_OVERLAP_RATIO = 0.10
MIN_BOUNDARY_RATIO = 0.60
BOUNDARIES = ("\n\n", "\n", "。", "；", "，")


def split_docs(docs: list[Document]) -> list[Document]:
    chunks: list[Document] = []
    for doc in docs:
        text = _normalize(doc.page_content)
        start = 0
        index = 0
        previous_end = 0
        while start < len(text):
            end = _find_end(text, start)
            chunk_text = text[start:end].strip()
            if chunk_text:
                overlap_chars = max(0, previous_end - start)
                chunks.append(_make_chunk(doc, chunk_text, index, start, end, overlap_chars))
                index += 1
            if end >= len(text):
                break
            overlap = max(1, round((end - start) * CHUNK_OVERLAP_RATIO))
            previous_end = end
            start = max(end - overlap, start + 1)
    return chunks


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _find_end(text: str, start: int) -> int:
    hard_end = min(start + CHUNK_SIZE, len(text))
    if hard_end == len(text):
        return hard_end
    search_start = start + round(CHUNK_SIZE * MIN_BOUNDARY_RATIO)
    window = text[search_start:hard_end]
    best_end = -1
    for boundary in BOUNDARIES:
        position = window.rfind(boundary)
        if position >= 0:
            best_end = max(best_end, search_start + position + len(boundary))
    return best_end if best_end > start else hard_end


def _make_chunk(
    doc: Document,
    text: str,
    index: int,
    start: int,
    end: int,
    overlap_chars: int,
) -> Document:
    metadata = dict(doc.metadata)
    metadata.update({
        "chunk": index,
        "chunk_start": start,
        "chunk_end": end,
        "chunk_size": len(text),
        "overlap_chars": overlap_chars,
        "overlap_ratio": CHUNK_OVERLAP_RATIO,
    })
    return Document(page_content=text, metadata=metadata)
