import pytest

from engine.state_manager import StaleVersionError, save_session_state
from models.game import GameSession
from models.user import User
from models.world import World, WorldCharacter


@pytest.mark.asyncio
async def test_save_session_state_increments_version(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()
    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()
    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"current_location": "镇口"},
        rounds_played=0,
    )
    db.add(session)
    await db.commit()

    new_version = await save_session_state(
        db,
        session.id,
        {"current_location": "茶摊"},
        expected_version=0,
    )
    await db.commit()
    await db.refresh(session)

    assert new_version == 1
    assert session.version == 1
    assert session.game_state == {"current_location": "茶摊"}


@pytest.mark.asyncio
async def test_save_session_state_rejects_stale_version(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()
    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="base",
        script_setting="legacy",
        status="published",
    )
    db.add(world)
    await db.flush()
    character = WorldCharacter(
        world_id=world.id,
        name="调查员",
        personality="",
        playable=True,
        description="",
        abilities=[],
        initial_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()
    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"current_location": "镇口"},
        rounds_played=0,
    )
    db.add(session)
    await db.commit()

    await save_session_state(db, session.id, {"current_location": "茶摊"}, expected_version=0)
    await db.commit()

    with pytest.raises(StaleVersionError):
        await save_session_state(db, session.id, {"current_location": "码头"}, expected_version=0)
