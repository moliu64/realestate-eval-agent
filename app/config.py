"""Application configuration.

All runtime settings are read from environment variables (or a local ``.env``
file). The configuration object is immutable and cached so every layer of the
application sees the same values.
"""

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "app" / "web" / "static"


def _resolve_path(path_value: str) -> str:
    path = Path(path_value).expanduser()
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def _read_auth_users() -> dict[str, dict[str, str]]:
    raw_users = os.getenv("AUTH_USERS_JSON", "{}").strip()
    if not raw_users:
        return {}
    try:
        parsed_users = json.loads(raw_users)
    except json.JSONDecodeError as exc:
        raise ValueError("AUTH_USERS_JSON 必须是合法 JSON。") from exc
    if not isinstance(parsed_users, dict):
        raise ValueError("AUTH_USERS_JSON 必须是 JSON 对象。")
    return {
        str(username): {
            "password": str(details.get("password", "")),
            "role": str(details.get("role", "user")),
        }
        for username, details in parsed_users.items()
        if isinstance(details, dict) and details.get("password")
    }


@dataclass(frozen=True)
class Config:
    """Immutable application settings."""

    base_url: str | None
    api_key: str | None
    model: str
    llm_timeout_seconds: int
    embedding_model: str
    docs_dir: str
    vector_db_dir: str
    sessions_dir: str
    auth_users_file: str
    retrieval_top_k: int
    min_relevance_score: float
    host: str
    port: int
    vision_base_url: str | None
    vision_api_key: str | None
    vision_model: str
    auth_users: dict[str, dict[str, str]]
    public_host: str
    log_level: str
    max_upload_bytes: int


@lru_cache(maxsize=1)
def load_config() -> Config:
    """Load and validate configuration from the environment exactly once."""

    load_dotenv()

    try:
        llm_timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    except ValueError as exc:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须是整数。") from exc
    if llm_timeout_seconds <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须大于 0。")

    try:
        retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "4"))
        min_relevance_score = float(os.getenv("MIN_RELEVANCE_SCORE", "0.5"))
        port = int(os.getenv("APP_PORT", "8000"))
        max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
    except ValueError as exc:
        raise ValueError("数值型配置格式不正确，请检查 RETRIEVAL_TOP_K、MIN_RELEVANCE_SCORE、APP_PORT、MAX_UPLOAD_MB。") from exc
    if retrieval_top_k <= 0:
        raise ValueError("RETRIEVAL_TOP_K 必须大于 0。")
    if not 0 <= min_relevance_score <= 1:
        raise ValueError("MIN_RELEVANCE_SCORE 必须位于 0 到 1 之间。")
    if not 0 < port < 65536:
        raise ValueError("APP_PORT 必须是 1–65535 之间的端口号。")

    return Config(
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        api_key=os.getenv("OPENAI_API_KEY") or None,
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_timeout_seconds=llm_timeout_seconds,
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        docs_dir=_resolve_path(os.getenv("DOCS_DIR", "data/docs")),
        vector_db_dir=_resolve_path(os.getenv("VECTOR_DB_DIR", "data/vector_db")),
        sessions_dir=_resolve_path(os.getenv("SESSIONS_DIR", "data/sessions")),
        auth_users_file=_resolve_path(os.getenv("AUTH_USERS_FILE", "data/auth_users.json")),
        retrieval_top_k=retrieval_top_k,
        min_relevance_score=min_relevance_score,
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=port,
        vision_base_url=os.getenv("VISION_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1") or None,
        vision_api_key=os.getenv("VISION_API_KEY") or None,
        vision_model=os.getenv("VISION_MODEL", "qwen-vl-plus"),
        auth_users=_read_auth_users(),
        public_host=os.getenv("PUBLIC_HOST", "").strip().lower(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
    )
