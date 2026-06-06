"""Phase 2.D.3 — batch_query_npc_memories: single SQL + single embed for N NPCs."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base
from engine.memory_manager import MemoryManager
from models.memory import MemoryEntry


_TEST_DB_URL = "sqlite+aiosqlite:///./test_batch_memory.db"


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


async def _seed(db: AsyncSession, sid: str, rows: list[dict]) -> None:
    for r in rows:
        db.add(
            MemoryEntry(
                session_id=sid,
                memory_type="general",
                content=r["content"],
                round_number=r.get("round", 1),
                importance=r.get("importance", 5),
                related_npc=r["npc"],
                embedding=r.get("embedding"),
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_batch_returns_empty_dict_for_no_npcs(db):
    mm = MemoryManager()
    out = await mm.batch_query_npc_memories(db, str(uuid.uuid4()), [])
    assert out == {}


@pytest.mark.asyncio
async def test_batch_groups_by_npc_name(db):
    sid = str(uuid.uuid4())
    await _seed(
        db,
        sid,
        [
            {"npc": "A", "content": "A1", "importance": 9},
            {"npc": "B", "content": "B1", "importance": 7},
            {"npc": "A", "content": "A2", "importance": 5},
            {"npc": "C", "content": "C1", "importance": 8},
        ],
    )
    mm = MemoryManager()
    out = await mm.batch_query_npc_memories(db, sid, ["A", "B", "C"], limit_per_npc=10)
    assert sorted(out.keys()) == ["A", "B", "C"]
    assert [m["content"] for m in out["A"]] == ["A1", "A2"]
    assert [m["content"] for m in out["B"]] == ["B1"]
    assert [m["content"] for m in out["C"]] == ["C1"]


@pytest.mark.asyncio
async def test_batch_includes_unmentioned_npc_with_empty_list(db):
    sid = str(uuid.uuid4())
    await _seed(db, sid, [{"npc": "A", "content": "A1"}])
    mm = MemoryManager()
    out = await mm.batch_query_npc_memories(db, sid, ["A", "Z"], limit_per_npc=5)
    assert out["A"] == [{
        "memory_type": "general", "content": "A1", "round_number": 1, "importance": 5
    }]
    assert out["Z"] == []


@pytest.mark.asyncio
async def test_batch_embeds_query_text_only_once(db, monkeypatch):
    """Embedding API must be called exactly once across all NPCs in a turn."""
    sid = str(uuid.uuid4())
    await _seed(
        db,
        sid,
        [
            {"npc": "A", "content": "alpha", "embedding": [1.0, 0.0]},
            {"npc": "B", "content": "beta", "embedding": [0.0, 1.0]},
        ],
    )
    embed_calls: list[str] = []

    async def _stub_embed(text: str):
        embed_calls.append(text)
        return [0.5, 0.5]

    monkeypatch.setattr("engine.memory_manager.embed_text", _stub_embed)
    mm = MemoryManager()
    out = await mm.batch_query_npc_memories(
        db, sid, ["A", "B"], limit_per_npc=5, query_text="something"
    )
    assert embed_calls == ["something"]
    # Both got the rerank treatment (similarity field present).
    assert out["A"][0]["similarity"] is not None
    assert out["B"][0]["similarity"] is not None


@pytest.mark.asyncio
async def test_batch_falls_back_to_importance_when_no_query_text(db):
    sid = str(uuid.uuid4())
    await _seed(
        db,
        sid,
        [
            {"npc": "A", "content": "low", "importance": 3, "embedding": [1.0]},
            {"npc": "A", "content": "high", "importance": 9, "embedding": [0.0]},
        ],
    )
    mm = MemoryManager()
    out = await mm.batch_query_npc_memories(db, sid, ["A"], limit_per_npc=2)
    # Importance order: high, low.
    assert [m["content"] for m in out["A"]] == ["high", "low"]
    assert all("similarity" not in m for m in out["A"])


@pytest.mark.asyncio
async def test_batch_respects_limit_per_npc(db):
    sid = str(uuid.uuid4())
    await _seed(
        db,
        sid,
        [{"npc": "A", "content": f"M{i}", "importance": 10 - i} for i in range(8)],
    )
    mm = MemoryManager()
    out = await mm.batch_query_npc_memories(db, sid, ["A"], limit_per_npc=3)
    assert len(out["A"]) == 3
    # Top by importance.
    assert [m["content"] for m in out["A"]] == ["M0", "M1", "M2"]
