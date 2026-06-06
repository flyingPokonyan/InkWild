import pytest
from sqlalchemy import select

from models.world import Ending, Event, World, WorldCharacter
from seeds.seed import seed_database


@pytest.mark.asyncio
async def test_seed_database_loads_wuyinzhen_data(db, test_engine, test_session_factory):
    world_id = await seed_database(db_engine=test_engine, session_factory=test_session_factory)

    world = await db.get(World, world_id)
    assert world is not None
    assert world.name == "雾隐镇"
    assert world.genre == "悬疑"

    world_chars = (await db.execute(select(WorldCharacter).where(WorldCharacter.world_id == world_id))).scalars().all()
    events = (await db.execute(select(Event).where(Event.world_id == world_id))).scalars().all()
    endings = (await db.execute(select(Ending).where(Ending.world_id == world_id))).scalars().all()

    npcs = [c for c in world_chars if not c.playable]
    playable = [c for c in world_chars if c.playable]

    assert len(npcs) == 4
    assert len(playable) == 3
    assert len(events) == 6
    assert len(endings) == 4
