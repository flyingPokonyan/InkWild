"""Phase 1.B.4 — NPC voice anchor: feed back recent self-utterances."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from engine.memory_manager import MemoryManager
from engine.prompts import build_npc_system
from models.game import Message


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


async def _seed_messages(db: AsyncSession, session_id: str, rows: list[dict]) -> None:
    for row in rows:
        db.add(
            Message(
                session_id=session_id,
                role=row.get("role", "assistant"),
                content=row.get("content", "..."),
                npc_dialogues=row.get("npc_dialogues"),
                created_at=datetime.now(timezone.utc),
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_get_npc_recent_utterances_returns_newest_first(db):
    sid = str(uuid.uuid4())
    await _seed_messages(
        db,
        sid,
        [
            {"npc_dialogues": {"王福": "茶刚泡好。"}},
            {"npc_dialogues": {"王福": "请进，先生。"}},
            {"npc_dialogues": {"王福": "你又来了。"}},
        ],
    )
    mm = MemoryManager()
    result = await mm.get_npc_recent_utterances(db, sid, "王福", limit=3)
    # Newest first.
    assert result == ["你又来了。", "请进，先生。", "茶刚泡好。"]


@pytest.mark.asyncio
async def test_get_npc_recent_utterances_filters_by_npc_name(db):
    sid = str(uuid.uuid4())
    await _seed_messages(
        db,
        sid,
        [
            {"npc_dialogues": {"王福": "我说一句。", "赵姐": "我也说一句。"}},
            {"npc_dialogues": {"赵姐": "今天好热。"}},
            {"npc_dialogues": {"王福": "你怎么样？"}},
        ],
    )
    mm = MemoryManager()
    result = await mm.get_npc_recent_utterances(db, sid, "王福", limit=5)
    assert result == ["你怎么样？", "我说一句。"]


@pytest.mark.asyncio
async def test_get_npc_recent_utterances_skips_user_and_null_rows(db):
    sid = str(uuid.uuid4())
    await _seed_messages(
        db,
        sid,
        [
            {"role": "user", "content": "我去茶摊", "npc_dialogues": None},
            {"npc_dialogues": None},  # assistant with no NPC speech
            {"npc_dialogues": {"王福": "嗯。"}},
        ],
    )
    mm = MemoryManager()
    result = await mm.get_npc_recent_utterances(db, sid, "王福", limit=3)
    assert result == ["嗯。"]


@pytest.mark.asyncio
async def test_get_npc_recent_utterances_respects_limit(db):
    sid = str(uuid.uuid4())
    await _seed_messages(
        db,
        sid,
        [{"npc_dialogues": {"王福": f"第{i}句"}} for i in range(10)],
    )
    mm = MemoryManager()
    result = await mm.get_npc_recent_utterances(db, sid, "王福", limit=3)
    assert len(result) == 3
    # Newest 3 from the seeded order.
    assert result == ["第9句", "第8句", "第7句"]


@pytest.mark.asyncio
async def test_get_npc_recent_utterances_empty_when_no_match(db):
    sid = str(uuid.uuid4())
    await _seed_messages(db, sid, [{"npc_dialogues": {"赵姐": "hi"}}])
    mm = MemoryManager()
    result = await mm.get_npc_recent_utterances(db, sid, "王福", limit=3)
    assert result == []


def test_build_npc_system_includes_voice_anchor_section_when_provided():
    text = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret=None,
        instruction="回应玩家",
        voice_anchor=["你又来了。", "请进，先生。"],
    )
    assert "你最近说过的话" in text
    assert "「你又来了。」" in text
    assert "「请进，先生。」" in text


def test_build_npc_system_omits_voice_anchor_section_when_empty():
    text = build_npc_system(
        npc_name="王福",
        npc_personality="忠厚寡言",
        npc_secret=None,
        instruction="回应玩家",
        voice_anchor=[],
    )
    assert "你最近说过的话" not in text
