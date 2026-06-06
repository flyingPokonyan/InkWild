"""Phase 1.B.2 — embedding_service unit tests."""
from __future__ import annotations

import pytest

from config import settings
from services import embedding_service


def test_cosine_similarity_basic():
    # Identical vectors → 1.0
    assert embedding_service.cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)
    # Orthogonal → 0.0
    assert embedding_service.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    # Opposite → -1.0
    assert embedding_service.cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_handles_empty_or_zero():
    assert embedding_service.cosine_similarity([], [1.0]) == 0.0
    assert embedding_service.cosine_similarity([1.0], []) == 0.0
    assert embedding_service.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_similarity_truncates_on_length_mismatch():
    # Mismatched length: silently uses the shorter one. Documented behavior.
    val = embedding_service.cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0])
    assert val == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_embed_texts_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "embedding_enabled", False)
    embedding_service.reset_client_cache()
    result = await embedding_service.embed_texts(["hello", "world"])
    assert result == [None, None]


@pytest.mark.asyncio
async def test_embed_texts_returns_none_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "embedding_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_key", "")
    embedding_service.reset_client_cache()
    result = await embedding_service.embed_texts(["hello"])
    assert result == [None]


@pytest.mark.asyncio
async def test_embed_texts_handles_empty_input():
    assert await embedding_service.embed_texts([]) == []


@pytest.mark.asyncio
async def test_embed_texts_handles_provider_failure(monkeypatch):
    """When the provider raises, every input maps to None (no exception)."""
    monkeypatch.setattr(settings, "embedding_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_key", "fake-key")
    embedding_service.reset_client_cache()

    class _BoomEmbeddings:
        async def create(self, **kwargs):
            raise RuntimeError("upstream down")

    class _BoomClient:
        embeddings = _BoomEmbeddings()

    monkeypatch.setattr(embedding_service, "_get_client", lambda: _BoomClient())
    result = await embedding_service.embed_texts(["a", "b"])
    assert result == [None, None]


@pytest.mark.asyncio
async def test_embed_texts_skips_blank_strings(monkeypatch):
    """Blank/whitespace-only entries map to None without hitting the API."""
    monkeypatch.setattr(settings, "embedding_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_key", "fake-key")
    embedding_service.reset_client_cache()

    captured_inputs: list[list[str]] = []

    class _FakeData:
        def __init__(self, vec):
            self.embedding = vec

    class _FakeResponse:
        def __init__(self, vecs):
            self.data = [_FakeData(v) for v in vecs]

    class _FakeEmbeddings:
        async def create(self, **kwargs):
            captured_inputs.append(kwargs["input"])
            return _FakeResponse([[0.1, 0.2, 0.3] for _ in kwargs["input"]])

    class _FakeClient:
        embeddings = _FakeEmbeddings()

    monkeypatch.setattr(embedding_service, "_get_client", lambda: _FakeClient())
    result = await embedding_service.embed_texts(["有内容", "", "   ", "另一条"])
    # Two real inputs, two None entries.
    assert captured_inputs == [["有内容", "另一条"]]
    assert result[0] == [0.1, 0.2, 0.3]
    assert result[1] is None
    assert result[2] is None
    assert result[3] == [0.1, 0.2, 0.3]
