"""Phase 1.B.2 — semantic recall via cosine similarity rerank."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base
from engine.memory_manager import MemoryManager
from models.memory import MemoryEntry
from services import embedding_service


_TEST_DB_URL = "sqlite+aiosqlite:///./test_semantic.db"


@pytest.fixture
async def db():
    engine = create_async_engine(_TEST_DB_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _stub_embed_text(text: str, vector: list[float]):
    """Build a monkeypatchable embed_text that returns ``vector``."""

    async def _impl(_text):
        return vector

    return _impl


async def _seed_session(db: AsyncSession) -> str:
    """Return a valid UUID string usable as memory_entries.session_id.

    SQLite ignores FK constraints by default (no ``PRAGMA foreign_keys=ON``),
    so we can skip seeding the parent game_sessions row entirely.
    """
    return str(uuid.uuid4())


async def _seed_memories(db: AsyncSession, session_id: str, rows: list[dict]) -> None:
    for row in rows:
        db.add(
            MemoryEntry(
                session_id=session_id,
                memory_type=row.get("memory_type", "general"),
                content=row["content"],
                round_number=row.get("round_number", 0),
                importance=row.get("importance", 5),
                related_npc=row.get("related_npc"),
                embedding=row.get("embedding"),
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_query_npc_memories_falls_back_when_no_query_text(db, monkeypatch):
    """No query_text → legacy importance/round ordering, no embedding call."""
    embed_calls = []

    async def _track_embed(text):
        embed_calls.append(text)
        return [1.0]

    monkeypatch.setattr("engine.memory_manager.embed_text", _track_embed)

    session_id = await _seed_session(db)
    await _seed_memories(
        db,
        session_id,
        [
            {"content": "重要旧事", "importance": 9, "round_number": 1, "related_npc": "王福"},
            {"content": "次要新事", "importance": 3, "round_number": 5, "related_npc": "王福"},
        ],
    )

    mm = MemoryManager()
    result = await mm.query_npc_memories(db, session_id, "王福", limit=2)
    assert [r["content"] for r in result] == ["重要旧事", "次要新事"]
    assert embed_calls == []


@pytest.mark.asyncio
async def test_query_npc_memories_falls_back_when_no_embeddings(db, monkeypatch):
    """query_text given but no candidate has an embedding → legacy ordering."""
    monkeypatch.setattr(
        "engine.memory_manager.embed_text",
        _stub_embed_text("anything", [1.0, 0.0]),
    )
    session_id = await _seed_session(db)
    await _seed_memories(
        db,
        session_id,
        [
            {"content": "事件 A", "importance": 9, "related_npc": "王福", "embedding": None},
            {"content": "事件 B", "importance": 3, "related_npc": "王福", "embedding": None},
        ],
    )
    mm = MemoryManager()
    result = await mm.query_npc_memories(db, session_id, "王福", limit=2, query_text="检查门槛")
    # Importance ordering preserved; no semantic field.
    assert [r["content"] for r in result] == ["事件 A", "事件 B"]
    assert all("similarity" not in r for r in result)


@pytest.mark.asyncio
async def test_query_npc_memories_reranks_by_cosine_similarity(db, monkeypatch):
    """Lower-importance but semantically relevant entry beats high-importance unrelated entry."""
    # Query embedding "matches" the second row strongly.
    monkeypatch.setattr(
        "engine.memory_manager.embed_text",
        _stub_embed_text("门槛血迹", [0.0, 1.0]),
    )

    session_id = await _seed_session(db)
    await _seed_memories(
        db,
        session_id,
        [
            # Highest importance but semantically distant from the query.
            {
                "content": "无关闲聊",
                "importance": 9,
                "round_number": 1,
                "related_npc": "王福",
                "embedding": [1.0, 0.0],
            },
            # Lower importance but semantically aligned.
            {
                "content": "门槛上的血迹",
                "importance": 3,
                "round_number": 2,
                "related_npc": "王福",
                "embedding": [0.0, 1.0],
            },
            # Middle ground.
            {
                "content": "走廊有脚印",
                "importance": 5,
                "round_number": 3,
                "related_npc": "王福",
                "embedding": [0.5, 0.5],
            },
        ],
    )

    mm = MemoryManager()
    result = await mm.query_npc_memories(
        db, session_id, "王福", limit=3, query_text="检查门槛血迹"
    )
    # First result must be the semantically aligned entry, not the highest-importance one.
    assert result[0]["content"] == "门槛上的血迹"
    assert result[0]["similarity"] == pytest.approx(1.0)
    # All three returned, sorted by cosine.
    assert [r["content"] for r in result] == ["门槛上的血迹", "走廊有脚印", "无关闲聊"]


@pytest.mark.asyncio
async def test_query_npc_memories_keeps_unembedded_rows_at_bottom(db, monkeypatch):
    """Mixed candidates: embedded rows ranked by cosine, NULL-embedding rows last."""
    monkeypatch.setattr(
        "engine.memory_manager.embed_text",
        _stub_embed_text("查询", [1.0, 0.0]),
    )

    session_id = await _seed_session(db)
    await _seed_memories(
        db,
        session_id,
        [
            {
                "content": "有 embedding 的低相关",
                "importance": 5,
                "related_npc": "王福",
                "embedding": [0.0, 1.0],
            },
            {
                "content": "有 embedding 的高相关",
                "importance": 5,
                "related_npc": "王福",
                "embedding": [1.0, 0.0],
            },
            {"content": "无 embedding 的高重要", "importance": 9, "related_npc": "王福"},
        ],
    )

    mm = MemoryManager()
    result = await mm.query_npc_memories(
        db, session_id, "王福", limit=3, query_text="查询"
    )
    assert result[0]["content"] == "有 embedding 的高相关"
    # NULL embedding row is sorted last regardless of importance.
    assert result[-1]["content"] == "无 embedding 的高重要"
    assert result[-1]["similarity"] is None


@pytest.mark.asyncio
async def test_attach_embeddings_handles_failure_gracefully(monkeypatch):
    """When embed_texts returns all-None, every entry just gets embedding=None."""

    async def _all_none(texts):
        return [None] * len(texts)

    monkeypatch.setattr("engine.memory_manager.embed_texts", _all_none)
    mm = MemoryManager()
    entries = [{"content": "a"}, {"content": "b"}]
    out = await mm.attach_embeddings(entries)
    assert out is entries  # in-place
    assert all(entry["embedding"] is None for entry in entries)


@pytest.mark.asyncio
async def test_attach_embeddings_attaches_vectors_when_available(monkeypatch):
    async def _fake_embed(texts):
        return [[0.1] * len(t) for t in texts]

    monkeypatch.setattr("engine.memory_manager.embed_texts", _fake_embed)
    mm = MemoryManager()
    entries = [{"content": "ab"}, {"content": "abc"}]
    await mm.attach_embeddings(entries)
    assert entries[0]["embedding"] == [0.1, 0.1]
    assert entries[1]["embedding"] == [0.1, 0.1, 0.1]


@pytest.mark.asyncio
async def test_attach_embeddings_noop_on_empty():
    mm = MemoryManager()
    out = await mm.attach_embeddings([])
    assert out == []
