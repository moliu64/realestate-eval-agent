import json
from pathlib import Path
import unittest

from app.config import load_config
from app.rag.retriever import retrieve
from app.rag.vectorstore import load_vectorstore


class RetrieverTest(unittest.TestCase):
    def test_vectorstore_has_chunks(self):
        config = load_config()
        store = load_vectorstore(config.vector_db_dir)
        self.assertGreater(len(store.get(include=[])["ids"]), 0)

    def test_retrieval_hits_expected_sources(self):
        cases = [
            json.loads(line)
            for line in Path("tests/eval_questions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        hits = 0
        for case in cases:
            results = retrieve(case["question"], k=4)
            sources = {doc.metadata.get("source") for doc, _ in results}
            if case["expected_source"] in sources:
                hits += 1

        self.assertGreaterEqual(hits, 7)


if __name__ == "__main__":
    unittest.main()
