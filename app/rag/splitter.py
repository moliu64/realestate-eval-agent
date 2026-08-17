from langchain_core.documents import Document

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _split_long_text(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def split_docs(docs: list[Document]) -> list[Document]:
    chunks: list[Document] = []
    for doc in docs:
        # Minimal decision: paragraph-first splitting keeps formulas and tables intact for the demo.
        blocks = [block.strip() for block in doc.page_content.split("\n\n") if block.strip()]
        current = ""
        index = 0

        for block in blocks:
            candidate = f"{current}\n\n{block}".strip() if current else block
            if len(candidate) <= CHUNK_SIZE:
                current = candidate
                continue

            if current:
                chunks.append(_make_chunk(doc, current, index))
                index += 1
                current = ""

            if len(block) > CHUNK_SIZE:
                for part in _split_long_text(block, CHUNK_SIZE, CHUNK_OVERLAP):
                    chunks.append(_make_chunk(doc, part, index))
                    index += 1
            else:
                current = block

        if current:
            chunks.append(_make_chunk(doc, current, index))

    return chunks


def _make_chunk(doc: Document, text: str, index: int) -> Document:
    metadata = dict(doc.metadata)
    metadata["chunk"] = index
    return Document(page_content=text, metadata=metadata)
