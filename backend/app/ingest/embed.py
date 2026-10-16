import hashlib
import math
import re
from typing import Sequence

EMBEDDING_DIM = 384


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return [0.0] * len(vec)
    return [round(x / norm, 6) for x in vec]


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate a deterministic 384-dimensional unit-normalized embedding vector.
    Uses token n-grams and hashed feature projection for semantic stability and fast local execution
    without heavy deep-learning dependencies.
    """
    if not text:
        return [0.0] * dim

    vec = [0.0] * dim
    tokens = re.findall(r"\w+", text.lower())

    # Single tokens (primary semantic signal)
    for token in tokens:
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign * 2.0

    # Bi-grams for local phrase context
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]}_{tokens[i+1]}"
        h = int(hashlib.sha256(bigram.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign * 1.0

    # Tri-grams
    for i in range(len(tokens) - 2):
        trigram = f"{tokens[i]}_{tokens[i+1]}_{tokens[i+2]}"
        h = int(hashlib.sha256(trigram.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign * 0.5

    return _normalize(vec)


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(v1) != len(v2) or not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
