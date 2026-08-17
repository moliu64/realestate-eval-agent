from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.config import load_config


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    config = load_config()
    if not config.api_key or config.api_key == "your-api-key-here":
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Copy .env.example to .env and fill in a real key."
        )

    kwargs = {
        "model": config.model,
        "api_key": config.api_key,
        "temperature": 0.2,
        "timeout": config.llm_timeout_seconds,
        "max_retries": 1,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url

    return ChatOpenAI(**kwargs)
