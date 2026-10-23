from functools import lru_cache
import os

from langchain_core.embeddings import Embeddings

from app.config import load_config


class LocalBgeEmbeddings(Embeddings):
    """Sentence-transformers BGE embedding model loaded lazily from local cache."""

    def __init__(self, model_name: str) -> None:
        # Force offline loading: the model is expected to be cached locally.
        # Set HF_HUB_OFFLINE=0 explicitly if the first download is needed.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer

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
