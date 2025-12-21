from functools import lru_cache
from typing import List
import os

from openai import OpenAI
from sentence_transformers import SentenceTransformer


OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDING_DIMENSION = 1536

BGE_EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
BGE_EMBEDDING_DIMENSION = 1024


@lru_cache(maxsize=1)
def _load_bge_model() -> SentenceTransformer:
    # Cache the model across API workers so we don't reload on each request.
    return SentenceTransformer(BGE_EMBEDDING_MODEL)


def _openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required for OpenAI embeddings.")
    return OpenAI(api_key=api_key)


def embed_texts(texts: List[str], embedding_model: str) -> List[List[float]]:
    """
    Embed passages using the selected embedding model.
    """
    if not texts:
        return []
    if embedding_model == "openai-embeddings":
        client = _openai_client()
        resp = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in resp.data]
    if embedding_model == "bge-large-en-v1.5":
        model = _load_bge_model()
        prefixed = [f"passage: {t}" for t in texts]
        vectors = model.encode(
            prefixed,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vectors.tolist()
    raise ValueError(f"Unsupported embedding model: {embedding_model}")


def embed_query(query: str, embedding_model: str) -> List[float]:
    """
    Embed a single query string with the selected embedding model.
    """
    if embedding_model == "openai-embeddings":
        client = _openai_client()
        resp = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=[query],
        )
        return resp.data[0].embedding
    if embedding_model == "bge-large-en-v1.5":
        model = _load_bge_model()
        vector = model.encode(
            [f"query: {query}"],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
        return vector.tolist()
    raise ValueError(f"Unsupported embedding model: {embedding_model}")


def embedding_dimension(embedding_model: str) -> int:
    if embedding_model == "openai-embeddings":
        return OPENAI_EMBEDDING_DIMENSION
    if embedding_model == "bge-large-en-v1.5":
        return BGE_EMBEDDING_DIMENSION
    raise ValueError(f"Unsupported embedding model: {embedding_model}")
