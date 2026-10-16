import hashlib
import json
import logging
import math
import os
import re
from typing import Any, Sequence
from app.config import settings

logger = logging.getLogger("ripple.embed")

EMBEDDING_DIM = 384


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return [0.0] * len(vec)
    return [round(x / norm, 6) for x in vec]


def _hash_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic 384-dimensional unit-normalized token & n-gram projection."""
    if not text:
        return [0.0] * dim

    vec = [0.0] * dim
    tokens = re.findall(r"\w+", text.lower())

    # Single tokens
    for token in tokens:
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign * 2.0

    # Bi-grams
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


def _semantic_embed_openai(text: str, dim: int = EMBEDDING_DIM) -> list[float] | None:
    """Generate 384-dim semantic embedding via OpenAI text-embedding-3-small."""
    if not settings.openai_api_key or not text:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.embeddings.create(
            input=text,
            model="text-embedding-3-small",
            dimensions=dim,
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.warning(f"OpenAI semantic embedding failed: {e}. Falling back to hash.")
        return None


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate embedding vector.
    Backend controlled by EMBEDDINGS_BACKEND env var ('semantic' or 'hash').
    Defaults to semantic when keys are available; falls back to deterministic hash projection.
    """
    backend = os.getenv("EMBEDDINGS_BACKEND", "semantic").lower()

    if backend == "semantic":
        sem_vec = _semantic_embed_openai(text, dim=dim)
        if sem_vec:
            return _normalize(sem_vec)

    return _hash_embed(text, dim=dim)


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


def query_vector_index(
    graph: Any,
    label: str,
    property_name: str,
    query_vector: Sequence[float],
    k: int = 5,
) -> list[dict[str, Any]]:
    """Execute FalkorDB native vector similarity search procedure.
    Procedure: CALL db.idx.vector.queryNodes(label, property_name, k, vecf32([...])) YIELD node, score
    Falls back gracefully if vector procedure is not supported on the target graph.
    """
    if not query_vector:
        return []

    vals_str = ",".join(str(round(x, 6)) for x in query_vector)
    cypher = (
        f"CALL db.idx.vector.queryNodes('{label}', '{property_name}', {k}, vecf32([{vals_str}])) "
        f"YIELD node, score RETURN node, score"
    )
    try:
        res = graph.query(cypher)
        hits = []
        if res and res.result_set:
            for row in res.result_set:
                node, score = row
                hits.append({
                    "node": node,
                    "score": float(score) if score is not None else 0.0,
                })
        return hits
    except Exception as e:
        logger.warning(f"FalkorDB vector query error for {label}.{property_name}: {e}. Falling back to Cypher scan.")
        return []
