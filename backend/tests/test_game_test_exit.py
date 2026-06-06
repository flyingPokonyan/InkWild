import pytest
from sqlalchemy import select

from engine.state_manager import GameState
from models.game import GameSession, Message
from models.user import User
from models.world import Character, World
from services.game_service import GameService


class UnexpectedOrchestrator:
    async def process_action(self, *args, **kwargs):
        raise AssertionError("test exit command should bypass orchestrator")
        yield {}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["script", "free"])
async def test_test_exit_command_ends_session_without_calling_orchestrator(db, mode):
    user = User(nickname="测试玩家")
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
        script_setting="legacy" if mode == "script" else "",
        status="published",
    )
    db.add(world)
    await db.flush()

    character = Character(
        world_id=world.id,
        name="调查员",
        description="",
        abilities=[],
        starting_location="镇口",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    await db.flush()

    initial_state = GameState(
        current_time="第2天·夜晚",
        current_location="钟楼",
        player_inventory=["手电筒"],
        discovered_clues=[],
        npc_relations={},
        triggered_events=[],
        visited_locations=["镇口", "钟楼"],
        time_index=3,
        round_number=4,
    )
    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode=mode,
        status="playing",
        game_state=initial_state.to_dict(),
        rounds_played=4,
    )
    db.add(session)
    await db.commit()

    service = GameService(UnexpectedOrchestrator())

    events = [
        event
        async for event in service.process_action(
            db,
            user.id,
            session.id,
            "/结束测试",
        )
    ]

    assert [event["type"] for event in events] == ["narrative", "state_update", "ending", "done"]
    assert events[2]["ending_type"] == "test_exit"
    assert events[2]["title"] == "测试结束"
    assert "测试暗号" in events[0]["text"]
    assert events[1]["game_state"] == initial_state.to_dict()

    await db.refresh(session)
    assert session.status == "ended"
    assert session.ending_type == "test_exit"
    assert session.rounds_played == 4
    assert session.game_state == initial_state.to_dict()

    messages = (
        await db.execute(select(Message).where(Message.session_id == session.id).order_by(Message.id.asc()))
    ).scalars().all()
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "/结束测试"
    assert "测试暗号" in messages[1].content
