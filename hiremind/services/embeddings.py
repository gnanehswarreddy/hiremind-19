import hashlib
import importlib
import math
from functools import lru_cache


EMBEDDING_DIMENSION = 256


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / magnitude, 8) for value in vector]


@lru_cache(maxsize=1)
def _load_model():
    try:
        sentence_transformers = importlib.import_module("sentence_transformers")
    except ImportError:
        return None

    return sentence_transformers.SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")


def _fallback_embedding(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0] * dimension
    tokens = [token for token in (text or "").lower().split() if token]
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for index in range(dimension):
            vector[index] += ((digest[index % len(digest)] / 255.0) * 2) - 1
    return _normalize(vector)


def generate_embedding(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    model = _load_model()
    if model is None:
        return _fallback_embedding(text, dimension)

    embedding = model.encode(text or "", normalize_embeddings=True).tolist()
    if len(embedding) == dimension:
        return [round(value, 8) for value in embedding]
    if len(embedding) > dimension:
        return [round(value, 8) for value in embedding[:dimension]]

    padded = embedding + ([0.0] * (dimension - len(embedding)))
    return [round(value, 8) for value in padded]


def build_search_text(parts: list[str | None]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())
