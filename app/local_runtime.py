"""Local runtime helpers used by the launcher panel and the ``run.py status`` command.

Everything here is standard-library only (no Tkinter, no model imports) so it can
be used from a headless shell, tests and CI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

from app import __version__
from app.config import PROJECT_ROOT, load_config

SUPPORTED_DOC_SUFFIXES = {".md", ".txt", ".csv", ".pdf", ".docx", ".png", ".jpg", ".jpeg"}


@dataclass(frozen=True)
class ServiceSnapshot:
    running: bool
    version: str = ""
    service: str = ""


@dataclass(frozen=True)
class ProjectStatus:
    project_root: str
    python_version: str
    host: str
    port: int
    url: str
    service_running: bool
    service_version: str
    app_version: str
    llm_model: str
    embedding_model: str
    api_key_configured: bool
    docs_count: int
    vector_count: int | None
    vector_index_ready: bool

    def as_dict(self) -> dict:
        return asdict(self)


def service_url(host: str | None = None, port: int | None = None) -> str:
    config = load_config()
    resolved_host = host or config.host
    resolved_port = port or config.port
    browser_host = "127.0.0.1" if resolved_host in {"0.0.0.0", ""} else resolved_host
    return f"http://{browser_host}:{resolved_port}"


def probe_service(timeout: float = 1.0, host: str | None = None, port: int | None = None) -> ServiceSnapshot:
    """Return the health snapshot of the local web service."""

    url = f"{service_url(host, port)}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - offline / not started is a normal state
        return ServiceSnapshot(running=False)
    return ServiceSnapshot(
        running=True,
        version=str(payload.get("version", "")),
        service=str(payload.get("service", "")),
    )


def count_documents(docs_dir: str | None = None) -> int:
    path = Path(docs_dir or load_config().docs_dir)
    if not path.exists():
        return 0
    return sum(
        1
        for entry in path.iterdir()
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_DOC_SUFFIXES
    )


def count_vectors(vector_db_dir: str | None = None) -> int | None:
    """Read the Chroma SQLite index directly, without loading any model."""

    sqlite_path = Path(vector_db_dir or load_config().vector_db_dir) / "chroma.sqlite3"
    if not sqlite_path.exists():
        return None
    try:
        connection = sqlite3.connect(
            f"file:{sqlite_path.as_posix()}?mode=ro",
            uri=True,
            timeout=1.0,
        )
    except sqlite3.Error:
        return None
    try:
        return int(connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def collect_status() -> ProjectStatus:
    config = load_config()
    snapshot = probe_service(host=config.host, port=config.port)
    vectors = count_vectors(config.vector_db_dir)
    return ProjectStatus(
        project_root=str(PROJECT_ROOT),
        python_version=sys.version.split()[0],
        host=config.host,
        port=config.port,
        url=service_url(),
        service_running=snapshot.running,
        service_version=snapshot.version,
        app_version=__version__,
        llm_model=config.model,
        embedding_model=config.embedding_model,
        api_key_configured=bool(config.api_key and config.api_key != "your-api-key-here"),
        docs_count=count_documents(config.docs_dir),
        vector_count=vectors,
        vector_index_ready=bool(vectors),
    )
