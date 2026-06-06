import asyncio
import json
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from config import settings
from database import async_session, engine
from models import AuthIdentity, Ending, Event, User, World, WorldCharacter

SEED_DIR = Path(__file__).parent / "wuyinzhen"
TABLES_TO_CLEAR = [
    "case_board_history",
    "npc_reflections",
    "npc_relations",
    "generation_task_events",
    "token_usage",
    "generation_tasks",
    "ip_knowledge_packs",
    "script_drafts",
    "world_drafts",
    "memory_entries",
    "messages",
    "game_sessions",
    "endings",
    "events",
    "world_characters",
    "characters",
    "npcs",
    "scripts",
    "worlds",
    "web_sessions",
]


def _load_json(filename: str):
    return json.loads((SEED_DIR / filename).read_text(encoding="utf-8"))


async def ensure_dev_user(session) -> str:
    normalized_email = settings.dev_user_email.strip().lower()
    identity = (
        await session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "password",
                AuthIdentity.provider_user_id == normalized_email,
            )
        )
    ).scalar_one_or_none()

    if identity is not None:
        user = await session.get(User, identity.user_id)
        if user is not None:
            user.status = "active"
            user.nickname = user.nickname or "Pokonyan"
        identity.email = normalized_email
        identity.credential_hash = settings.dev_user_password_hash
        await session.flush()
        return str(user.id if user is not None else identity.user_id)

    user = User(status="active", nickname="Pokonyan")
    session.add(user)
    await session.flush()
    session.add(
        AuthIdentity(
            user_id=user.id,
            provider="password",
            provider_user_id=normalized_email,
            credential_hash=settings.dev_user_password_hash,
            email=normalized_email,
            profile={"source": "seed"},
        )
    )
    await session.flush()
    return str(user.id)


async def seed_database(
    db_engine: AsyncEngine = engine,
    session_factory: async_sessionmaker = async_session,
) -> str:
    async with db_engine.begin() as connection:
        for table in TABLES_TO_CLEAR:
            await connection.execute(text(f"DELETE FROM {table}"))

    async with session_factory() as session:
        world_data = _load_json("world.json")
        world = World(**world_data)
        session.add(world)
        await session.flush()

        # Load unified world_characters (NPC + playable characters)
        playable_ids: list[str] = []
        for char_data in _load_json("world_characters.json"):
            wc = WorldCharacter(world_id=world.id, **char_data)
            session.add(wc)
            await session.flush()
            if wc.playable:
                playable_ids.append(str(wc.id))

        world.free_playable_character_ids = playable_ids

        for event_data in _load_json("events.json"):
            session.add(Event(world_id=world.id, **event_data))
            await session.flush()

        for ending_data in _load_json("endings.json"):
            session.add(Ending(world_id=world.id, **ending_data))
            await session.flush()

        await ensure_dev_user(session)
        await session.commit()
        return str(world.id)


async def seed():
    world_id = await seed_database()
    print(f"Seeded world: 雾隐镇 (id: {world_id})")


if __name__ == "__main__":
    asyncio.run(seed())
