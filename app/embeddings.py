from functools import lru_cache
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from app.config import load_config


class LocalBgeEmbeddings(Embeddings):
    def __init__(self, model_name: str) -> None:
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    config = load_config()
    return LocalBgeEmbeddings(config.embedding_model)
