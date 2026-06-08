"""A: the Director's recent-message window must be append-only between
compactions so DeepSeek's prefix cache survives. The old loader took the
`last max_context_rounds*2` messages, which slid forward one round every turn
and broke the cache right after the system prompt. The hard cap is now a
safety ceiling well above the compaction keep-size, so under normal operation
the query returns the full non-compacted history (a stable, growing prefix)."""

import pytest

from models.game import GameSession, Message
from models.user import User
from models.world import World, WorldCharacter
from services.game_service import load_recent_messages


async def _make_session(db):
    user = User(nickname="t")
    db.add(user)
    await db.flush()

    world = World(
        name="w",
        description="d",
        genre="g",
        era="e",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="b",
        script_setting="s",
        status="published",
    )
    db.add(world)
    await db.flush()

    character = WorldCharacter(
        world_id=world.id,
        name="c",
        personality="p",
        playable=True,
        description="d",
        abilities=[],
        initial_location="x",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()

    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="free",
        game_state={},
    )
    db.add(session)
    await db.commit()
    return session


@pytest.mark.asyncio
async def test_recent_messages_window_is_append_only_under_cap(db):
    session = await _make_session(db)

    # 40 messages: more than the old sliding limit (30), under the ceiling (60).
    for i in range(40):
        db.add(
            Message(
                session_id=session.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"m{i}",
            )
        )
    await db.commit()

    first = await load_recent_messages(db, session.id, limit=60)
    assert [m["content"] for m in first] == [f"m{i}" for i in range(40)]

    # Advance two rounds.
    for i in range(40, 44):
        db.add(Message(session_id=session.id, role="user", content=f"m{i}"))
    await db.commit()

    second = await load_recent_messages(db, session.id, limit=60)
    # Append-only: the earlier window is a prefix of the later one.
    assert [m["content"] for m in second][: len(first)] == [
        m["content"] for m in first
    ]
    assert [m["content"] for m in second] == [f"m{i}" for i in range(44)]


@pytest.mark.asyncio
async def test_recent_messages_window_excludes_compacted(db):
    session = await _make_session(db)
    db.add(Message(session_id=session.id, role="user", content="old", is_compressed=True))
    db.add(Message(session_id=session.id, role="assistant", content="kept"))
    await db.commit()

    window = await load_recent_messages(db, session.id, limit=60)
    assert [m["content"] for m in window] == ["kept"]
