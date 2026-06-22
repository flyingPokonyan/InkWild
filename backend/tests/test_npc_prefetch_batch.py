"""Batched NPC prefetch (orchestrator v2 hot path).

The v2 NPC block used to issue 3 serial DB queries per active NPC
(reflection / voice anchor / peer relations) inside a loop. These are now
batched into one set-based query each. This suite pins the contract: the
batch methods return results IDENTICAL to calling the single-NPC method per
NPC, so the optimization is behavior-preserving.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from engine.memory_manager import MemoryManager
from models.game import Message
from models.npc_reflection import NPCReflection
from models.npc_relation import NPCRelation
from services.npc_reflection_service import batch_get_reflections, get_reflection


_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db():
    engine = create_async_engine(_TEST_DB_URL, poolclass=StaticPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed_messages(db: AsyncSession, sid: str, rows: list[dict]) -> None:
    for row in rows:
        db.add(
            Message(
                session_id=sid,
                role=row.get("role", "assistant"),
                content=row.get("content", "..."),
                npc_dialogues=row.get("npc_dialogues"),
                created_at=datetime.now(timezone.utc),
            )
        )
    await db.commit()


# --------------------------------------------------------------------------
# voice anchor
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_recent_utterances_matches_single(db):
    sid = str(uuid.uuid4())
    await _seed_messages(
        db,
        sid,
        [
            {"npc_dialogues": {"王福": "茶刚泡好。", "赵姐": "今儿真热。"}},
            {"npc_dialogues": {"王福": "请进。"}},
            {"npc_dialogues": {"赵姐": "你来啦。"}},
            {"npc_dialogues": {"王福": "你又来了。", "钱叔": "嗯。"}},
        ],
    )
    mm = MemoryManager()
    names = ["王福", "赵姐", "钱叔", "孙婆"]  # 孙婆 never speaks
    batched = await mm.batch_get_npc_recent_utterances(db, sid, names, limit=3)
    for name in names:
        single = await mm.get_npc_recent_utterances(db, sid, name, limit=3)
        assert batched[name] == single, f"mismatch for {name}"
    # 孙婆 has no utterances → present with empty list.
    assert batched["孙婆"] == []


@pytest.mark.asyncio
async def test_batch_recent_utterances_empty_names(db):
    mm = MemoryManager()
    assert await mm.batch_get_npc_recent_utterances(db, str(uuid.uuid4()), [], limit=3) == {}


# --------------------------------------------------------------------------
# peer relations
# --------------------------------------------------------------------------

async def _seed_relations(db: AsyncSession, sid: str, rows: list[dict]) -> None:
    for r in rows:
        db.add(
            NPCRelation(
                session_id=sid,
                npc_a=r["npc_a"],
                npc_b=r["npc_b"],
                trust=r.get("trust", 0),
                relationship_label=r.get("label"),
                history_summary=r.get("history"),
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_batch_peer_relations_matches_single(db):
    sid = str(uuid.uuid4())
    await _seed_relations(
        db,
        sid,
        [
            {"npc_a": "王福", "npc_b": "赵姐", "trust": 6, "label": "邻居"},
            {"npc_a": "王福", "npc_b": "钱叔", "trust": -2, "label": "宿敌"},
            {"npc_a": "赵姐", "npc_b": "王福", "trust": 5, "label": "邻居"},
            {"npc_a": "钱叔", "npc_b": "孙婆", "trust": 1},  # not queried
        ],
    )
    mm = MemoryManager()
    names = ["王福", "赵姐", "孙婆"]  # 孙婆 has no outgoing relation
    batched = await mm.batch_get_npc_peer_relations(db, sid, names)
    for name in names:
        single = await mm.get_npc_peer_relations(db, sid, name)
        assert batched[name] == single, f"mismatch for {name}"
    assert batched["孙婆"] == []


# --------------------------------------------------------------------------
# reflections
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_reflections_matches_single(db):
    sid = str(uuid.uuid4())
    db.add(NPCReflection(session_id=sid, npc_name="王福", summary="我信任他。", last_memory_id=3))
    db.add(NPCReflection(session_id=sid, npc_name="赵姐", summary="我还在观望。", last_memory_id=5))
    await db.commit()

    names = ["王福", "赵姐", "钱叔"]  # 钱叔 has no reflection
    batched = await batch_get_reflections(db, sid, names)
    for name in names:
        single = await get_reflection(db, sid, name)
        if single is None:
            assert name not in batched
        else:
            assert batched[name].summary == single.summary
    assert "钱叔" not in batched


@pytest.mark.asyncio
async def test_batch_reflections_empty_names(db):
    assert await batch_get_reflections(db, str(uuid.uuid4()), []) == {}
