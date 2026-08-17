from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.rag.loader import load_docs


def main() -> None:
    config = load_config()
    docs = load_docs(config.docs_dir)
    if not 4 <= len(docs) <= 20:
        raise RuntimeError(f"Expected 4-20 supported docs, found {len(docs)}.")

    for doc in docs:
        source = doc.metadata["source"]
        text = doc.page_content
        if doc.metadata.get("file_type") == "md":
            if not text.lstrip().startswith("# "):
                raise RuntimeError(f"{source} must start with a level-1 markdown title.")
            if "\n## " not in text:
                raise RuntimeError(f"{source} should contain level-2 markdown sections.")

    print(f"Docs validation passed: {len(docs)} markdown files.")


if __name__ == "__main__":
    main()
