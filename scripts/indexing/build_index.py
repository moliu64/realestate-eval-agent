from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.rag.loader import load_docs
from app.rag.splitter import split_docs
from app.rag.vectorstore import build_vectorstore, load_vectorstore


def _count_documents(vectorstore) -> int:
    return len(vectorstore.get(include=[])["ids"])


def main() -> None:
    parser = ArgumentParser(description="Build the local Chroma vector database.")
    parser.add_argument("--rebuild", action="store_true", help="Delete existing vector DB before building.")
    parser.add_argument("--show-chunks", action="store_true", help="Print first 3 chunks for manual inspection.")
    args = parser.parse_args()

    config = load_config()
    docs = load_docs(config.docs_dir)
    chunks = split_docs(docs)
    if not chunks:
        raise RuntimeError("No chunks generated. Check data/docs/*.md.")

    if args.show_chunks:
        for chunk in chunks[:3]:
            print(f"\n--- {chunk.metadata.get('source')}#{chunk.metadata.get('chunk')} ---")
            print(chunk.page_content)

    build_vectorstore(chunks, config.vector_db_dir, rebuild=args.rebuild)
    loaded = load_vectorstore(config.vector_db_dir)
    count = _count_documents(loaded)
    print(f"Loaded {len(docs)} docs, generated {len(chunks)} chunks, vector DB count: {count}.")


if __name__ == "__main__":
    main()
