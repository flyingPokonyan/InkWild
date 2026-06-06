"""Phase 1 NPC reflection — should_reflect / reflect / maybe_reflect coverage."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database import Base
from models.memory import MemoryEntry
from models.npc_reflection import NPCReflection
from services import npc_reflection_service


_TEST_DB_URL = "sqlite+aiosqlite:///./test_npc_reflection.db"


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


class StubRouter:
    """Streams a fixed text response, mimics real LLMRouter event shape."""

    def __init__(self, text: str = "我对玩家的信任在加深。"):
        self.text = text
        self.calls: list[dict] = []

    async def stream_with_tools(self, messages, tools, system=None, max_tokens=2048, **kwargs):
        self.calls.append({"messages": messages, "tools": tools, "system": system})
        yield {"type": "text_delta", "text": self.text}


class FailingRouter:
    async def stream_with_tools(self, *args, **kwargs):
        raise RuntimeError("upstream down")
        yield  # unreachable; keeps async-generator shape


async def _seed_memories(db: AsyncSession, session_id: str, npc: str, count: int) -> list[int]:
    ids: list[int] = []
    for i in range(count):
        entry = MemoryEntry(
            session_id=session_id,
            memory_type="general",
            content=f"第{i+1}条新记忆",
            round_number=i + 1,
            importance=5,
            related_npc=npc,
        )
        db.add(entry)
        await db.flush()
        ids.append(entry.id)
    await db.commit()
    return ids


@pytest.mark.asyncio
async def test_should_reflect_false_when_disabled(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", False)
    sid = str(uuid.uuid4())
    await _seed_memories(db, sid, "王福", 10)
    assert await npc_reflection_service.should_reflect(db, sid, "王福") is False


@pytest.mark.asyncio
async def test_should_reflect_below_threshold(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    monkeypatch.setattr(settings, "npc_reflection_threshold", 5)
    sid = str(uuid.uuid4())
    await _seed_memories(db, sid, "王福", 4)
    assert await npc_reflection_service.should_reflect(db, sid, "王福") is False


@pytest.mark.asyncio
async def test_should_reflect_above_threshold(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    monkeypatch.setattr(settings, "npc_reflection_threshold", 5)
    sid = str(uuid.uuid4())
    await _seed_memories(db, sid, "王福", 5)
    assert await npc_reflection_service.should_reflect(db, sid, "王福") is True


@pytest.mark.asyncio
async def test_should_reflect_only_counts_new_memories_after_last_reflection(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    monkeypatch.setattr(settings, "npc_reflection_threshold", 3)
    sid = str(uuid.uuid4())
    ids = await _seed_memories(db, sid, "王福", 5)
    # Pretend the previous reflection already covered the first 4 entries.
    db.add(
        NPCReflection(
            session_id=sid,
            npc_name="王福",
            summary="老的反思",
            last_memory_id=ids[3],
        )
    )
    await db.commit()
    # Only 1 new entry > threshold(3) → should not trigger
    assert await npc_reflection_service.should_reflect(db, sid, "王福") is False
    # Add 3 more → now 4 new entries → should trigger
    await _seed_memories(db, sid, "王福", 3)
    assert await npc_reflection_service.should_reflect(db, sid, "王福") is True


@pytest.mark.asyncio
async def test_reflect_creates_new_row_on_first_run(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    sid = str(uuid.uuid4())
    await _seed_memories(db, sid, "王福", 3)
    router = StubRouter(text="我作为王福，对玩家的态度从警惕慢慢转向信任。")

    record = await npc_reflection_service.reflect(
        db,
        session_id=sid,
        npc_name="王福",
        npc_personality="忠厚寡言",
        llm_router=router,
    )

    assert record is not None
    assert "信任" in record.summary
    assert record.reflection_count == 1
    assert record.last_memory_id > 0
    # Re-fetch confirms persistence.
    fetched = await npc_reflection_service.get_reflection(db, sid, "王福")
    assert fetched is not None
    assert fetched.id == record.id


@pytest.mark.asyncio
async def test_reflect_updates_existing_row_and_advances_last_memory_id(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    sid = str(uuid.uuid4())
    initial_ids = await _seed_memories(db, sid, "王福", 3)
    router1 = StubRouter(text="第一次反思的内容。")
    record1 = await npc_reflection_service.reflect(
        db,
        session_id=sid,
        npc_name="王福",
        npc_personality="",
        llm_router=router1,
    )
    assert record1 is not None
    first_last_id = record1.last_memory_id

    # Add more memories, reflect again.
    await _seed_memories(db, sid, "王福", 3)
    router2 = StubRouter(text="新的反思——情节有了变化。")
    record2 = await npc_reflection_service.reflect(
        db,
        session_id=sid,
        npc_name="王福",
        npc_personality="",
        llm_router=router2,
    )

    assert record2 is not None
    assert record2.id == record1.id  # same row updated, not duplicated
    assert record2.reflection_count == 2
    assert record2.last_memory_id > first_last_id
    assert "新的反思" in record2.summary


@pytest.mark.asyncio
async def test_reflect_returns_none_with_no_new_memories(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    sid = str(uuid.uuid4())
    # No memories at all.
    router = StubRouter()
    result = await npc_reflection_service.reflect(
        db,
        session_id=sid,
        npc_name="王福",
        npc_personality="",
        llm_router=router,
    )
    assert result is None
    assert router.calls == []  # never called the LLM


@pytest.mark.asyncio
async def test_reflect_returns_none_when_llm_fails(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    sid = str(uuid.uuid4())
    await _seed_memories(db, sid, "王福", 3)
    result = await npc_reflection_service.reflect(
        db,
        session_id=sid,
        npc_name="王福",
        npc_personality="",
        llm_router=FailingRouter(),
    )
    assert result is None
    # And nothing persisted.
    assert (await npc_reflection_service.get_reflection(db, sid, "王福")) is None


@pytest.mark.asyncio
async def test_reflect_noop_when_disabled(db, monkeypatch):
    monkeypatch.setattr(settings, "npc_reflection_enabled", False)
    sid = str(uuid.uuid4())
    await _seed_memories(db, sid, "王福", 5)
    result = await npc_reflection_service.reflect(
        db,
        session_id=sid,
        npc_name="王福",
        npc_personality="",
        llm_router=StubRouter(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_maybe_reflect_swallows_errors(db, monkeypatch):
    """maybe_reflect must never raise — it's fire-and-forget by design."""
    monkeypatch.setattr(settings, "npc_reflection_enabled", True)
    sid = str(uuid.uuid4())
    await _seed_memories(db, sid, "王福", 5)

    # No exception even when the LLM blows up.
    await npc_reflection_service.maybe_reflect(
        db,
        session_id=sid,
        npc_name="王福",
        npc_personality="",
        llm_router=FailingRouter(),
    )
    # Nothing persisted (LLM failed).
    assert (await npc_reflection_service.get_reflection(db, sid, "王福")) is None
