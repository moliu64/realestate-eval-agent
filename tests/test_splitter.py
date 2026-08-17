import unittest

from langchain_core.documents import Document

from app.rag.splitter import CHUNK_OVERLAP_RATIO, split_docs


class SplitterTest(unittest.TestCase):
    def test_every_adjacent_chunk_overlaps_by_about_ten_percent(self):
        text = "。".join(f"第{i}段" + "内容" * 30 for i in range(30))
        chunks = split_docs([Document(page_content=text, metadata={"source": "测试.md"})])
        self.assertGreater(len(chunks), 2)
        for previous, current in zip(chunks, chunks[1:]):
            overlap = previous.metadata["chunk_end"] - current.metadata["chunk_start"]
            expected = round((previous.metadata["chunk_end"] - previous.metadata["chunk_start"]) * CHUNK_OVERLAP_RATIO)
            self.assertLessEqual(abs(overlap - expected), 1)
            self.assertGreater(overlap, 0)


if __name__ == "__main__":
    unittest.main()
