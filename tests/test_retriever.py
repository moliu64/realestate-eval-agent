import json
from pathlib import Path
import unittest

from app.config import PROJECT_ROOT, load_config
from app.rag.retriever import retrieve
from app.rag.vectorstore import load_vectorstore


class RetrieverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = load_config()
        try:
            cls.store = load_vectorstore(config.vector_db_dir)
            cls.ids = cls.store.get(include=[])["ids"]
        except Exception as exc:  # noqa: BLE001 - missing DB/model should skip, not fail CI
            raise unittest.SkipTest(f"vector database is not available: {exc}") from exc
        if not cls.ids:
            raise unittest.SkipTest(
                "vector database is empty; run `python run.py index` before running retrieval tests"
            )

    def test_vectorstore_has_chunks(self):
        self.assertGreater(len(self.ids), 0)

    def test_retrieval_hits_expected_sources(self):
        cases = [
            json.loads(line)
            for line in (PROJECT_ROOT / "tests/fixtures/eval_questions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        hits = 0
        for case in cases:
            try:
                results = retrieve(case["question"], k=4)
            except Exception as exc:  # noqa: BLE001 - embedding model may be unavailable offline
                raise unittest.SkipTest(f"embedding model is not available: {exc}") from exc
            sources = {doc.metadata.get("source") for doc, _ in results}
            if case["expected_source"] in sources:
                hits += 1

        self.assertGreaterEqual(hits, 7)


if __name__ == "__main__":
    unittest.main()
