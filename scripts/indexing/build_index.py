"""Build the local Chroma vector database from ``data/docs``."""

from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.rag.loader import load_docs
from app.rag.splitter import split_docs
from app.services.knowledge_service import build_index


def main() -> None:
    parser = ArgumentParser(description="Build the local Chroma vector database.")
    parser.add_argument("--rebuild", action="store_true", help="Delete the existing vector DB before building.")
    parser.add_argument("--show-chunks", action="store_true", help="Print the first 3 chunks for manual inspection.")
    args = parser.parse_args()

    config = load_config()
    if args.show_chunks:
        for chunk in split_docs(load_docs(config.docs_dir))[:3]:
            print(f"\n--- {chunk.metadata.get('source')}#{chunk.metadata.get('chunk')} ---")
            print(chunk.page_content)

    docs, chunks, count = build_index(rebuild=args.rebuild)
    print(f"Loaded {docs} docs, generated {chunks} chunks, vector DB count: {count}.")


if __name__ == "__main__":
    main()
