from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSION = 1024


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    # Cache the model across API workers so we don't reload on each request.
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed passages using BGE with the recommended prefix + normalization.
    """
    if not texts:
        return []
    model = _load_model()
    prefixed = [f"passage: {t}" for t in texts]
    vectors = model.encode(
        prefixed,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return vectors.tolist()


def embed_query(query: str) -> List[float]:
    """
    Embed a single query string with the BGE query instruction prefix.
    """
    model = _load_model()
    vector = model.encode(
        [f"query: {query}"],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0]
    return vector.tolist()


def embedding_model_name() -> str:
    return EMBEDDING_MODEL


def embedding_dimension() -> int:
    return EMBEDDING_DIMENSION
