"""Phase 1.B.2 — embedding generation for semantic memory recall.

Thin wrapper over an OpenAI-compatible embeddings endpoint (works with
OpenAI, DeepSeek embeddings, Together, Azure-compatible, etc.). All failures
return None instead of raising so memory writes degrade to the legacy
importance/round-ordered recall path.
"""
from __future__ import annotations

import asyncio
import math

import structlog
from openai import AsyncOpenAI

from config import settings

logger = structlog.get_logger()

_client: AsyncOpenAI | None = None
_client_key: tuple[str, str] | None = None


def _get_client() -> AsyncOpenAI | None:
    """Lazy-build the embedding client; rebuild if settings change at runtime."""
    global _client, _client_key
    if not settings.embedding_enabled:
        return None
    api_key = (settings.embedding_api_key or "").strip()
    base_url = (settings.embedding_base_url or "").strip()
    if not api_key:
        return None
    key = (api_key, base_url)
    if _client is None or _client_key != key:
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
        )
        _client_key = key
    return _client


def reset_client_cache() -> None:
    """Force the next call to rebuild the client. Used by tests."""
    global _client, _client_key
    _client = None
    _client_key = None


async def embed_texts(texts: list[str]) -> list[list[float] | None]:
    """Embed a batch of texts. Returns one embedding per input (None on failure).

    The embedding service is best-effort: any exception is logged once and
    every input maps to None. Callers MUST handle None entries.
    """
    if not texts:
        return []
    client = _get_client()
    if client is None:
        return [None] * len(texts)

    cleaned = [text if isinstance(text, str) and text.strip() else "" for text in texts]
    non_empty_indices = [i for i, t in enumerate(cleaned) if t]
    if not non_empty_indices:
        return [None] * len(texts)

    payload = [cleaned[i] for i in non_empty_indices]
    try:
        response = await asyncio.wait_for(
            client.embeddings.create(model=settings.embedding_model, input=payload),
            timeout=settings.embedding_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("embedding.timeout", text_count=len(payload))
        return [None] * len(texts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding.failed", error=str(exc), text_count=len(payload))
        return [None] * len(texts)

    embeddings_by_index: dict[int, list[float]] = {}
    for slot_index, item in zip(non_empty_indices, response.data):
        vec = list(getattr(item, "embedding", None) or [])
        if vec:
            embeddings_by_index[slot_index] = [float(x) for x in vec]

    return [embeddings_by_index.get(i) for i in range(len(texts))]


async def embed_text(text: str) -> list[float] | None:
    """Single-text convenience wrapper."""
    results = await embed_texts([text])
    return results[0] if results else None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine; safe on small candidate sets (≤ a few hundred entries).

    Returns 0.0 if either vector is empty/zero-norm. Does NOT validate length
    equality — caller is responsible for ensuring matching dimensions (a
    mismatch silently truncates to the shorter length).
    """
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(n):
        ai = a[i]
        bi = b[i]
        dot += ai * bi
        norm_a += ai * ai
        norm_b += bi * bi
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))
