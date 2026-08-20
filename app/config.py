from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import os

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(path_value: str) -> str:
    path = Path(path_value)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


@dataclass(frozen=True)
class Config:
    base_url: str | None
    api_key: str | None
    model: str
    llm_timeout_seconds: int
    embedding_model: str
    docs_dir: str
    vector_db_dir: str
    retrieval_top_k: int
    min_relevance_score: float
    host: str
    port: int
    vision_base_url: str | None
    vision_api_key: str | None
    vision_model: str
    admin_token: str | None
    auth_users: dict[str, dict[str, str]]
    cors_origins: tuple[str, ...]
    public_host: str


@lru_cache(maxsize=1)
def load_config() -> Config:
    load_dotenv()
    base_url = os.getenv("OPENAI_BASE_URL") or None
    api_key = os.getenv("OPENAI_API_KEY") or None
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    docs_dir = _resolve_path(os.getenv("DOCS_DIR", "data/docs"))
    vector_db_dir = _resolve_path(os.getenv("VECTOR_DB_DIR", "data/vector_db"))
    retrieval_top_k = int(os.getenv("RETRIEVAL_TOP_K", "4"))
    min_relevance_score = float(os.getenv("MIN_RELEVANCE_SCORE", "0.5"))
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    vision_base_url = os.getenv(
        "VISION_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ) or None
    vision_api_key = os.getenv("VISION_API_KEY") or None
    vision_model = os.getenv("VISION_MODEL", "qwen-vl-plus")
    admin_token = os.getenv("ADMIN_TOKEN") or None
    auth_users: dict[str, dict[str, str]] = {}
    raw_users = os.getenv("AUTH_USERS_JSON", "{}").strip()
    if raw_users:
        try:
            parsed_users = json.loads(raw_users)
            if isinstance(parsed_users, dict):
                auth_users = {
                    str(username): {
                        "password": str(details.get("password", "")),
                        "role": str(details.get("role", "user")),
                    }
                    for username, details in parsed_users.items()
                    if isinstance(details, dict) and details.get("password")
                }
        except json.JSONDecodeError as exc:
            raise ValueError("AUTH_USERS_JSON 必须是合法 JSON。") from exc
    cors_origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    )
    public_host = os.getenv("PUBLIC_HOST", "060115.top").strip().lower()

    return Config(
        base_url=base_url,
        api_key=api_key,
        model=model,
        llm_timeout_seconds=llm_timeout_seconds,
        embedding_model=embedding_model,
        docs_dir=docs_dir,
        vector_db_dir=vector_db_dir,
        retrieval_top_k=retrieval_top_k,
        min_relevance_score=min_relevance_score,
        host=host,
        port=port,
        vision_base_url=vision_base_url,
        vision_api_key=vision_api_key,
        vision_model=vision_model,
        admin_token=admin_token,
        auth_users=auth_users,
        cors_origins=cors_origins,
        public_host=public_host,
    )
