import socket
import tempfile
import unittest
from pathlib import Path

from app.local_runtime import count_documents, count_vectors, probe_service, service_url


class LocalRuntimeTest(unittest.TestCase):
    def test_count_documents_skips_unsupported_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.md").write_text("# a", encoding="utf-8")
            (root / "b.txt").write_text("b", encoding="utf-8")
            (root / "c.exe").write_bytes(b"binary")
            (root / "nested").mkdir()
            self.assertEqual(count_documents(str(root)), 2)

    def test_count_vectors_returns_none_when_index_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(count_vectors(temporary))

    def test_probe_service_reports_stopped_for_free_port(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        snapshot = probe_service(timeout=0.25, host="127.0.0.1", port=port)
        self.assertFalse(snapshot.running)

    def test_service_url_is_local(self) -> None:
        url = service_url()
        self.assertTrue(url.startswith("http://"))
        self.assertIn(":8000", url)


if __name__ == "__main__":
    unittest.main()
