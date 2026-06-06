import pytest
from sqlalchemy import select

from models.game import Message
from models.user import User
from models.world import World, WorldCharacter
from services.game_service import GameService


class FakeOpeningOrchestrator:
    async def process_action(self, *args, **kwargs):
        yield {"type": "narrative", "text": "浓雾从镇口漫过来。"}
        yield {
            "type": "state_update",
            "game_state": {"current_location": "镇口茶摊", "current_time": "第1天·上午"},
            "quick_actions": ["观察周围"],
            "triggered_events": [],
        }
        yield {
            "type": "done",
            "new_state": type(
                "FakeState",
                (),
                {"to_dict": lambda self: {"current_location": "镇口茶摊", "current_time": "第1天·上午"}},
            )(),
            "usage": None,
        }


@pytest.mark.asyncio
async def test_start_game_does_not_persist_internal_opening_prompt_as_user_message(db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()

    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="民国",
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
        name="外来调查员",
        personality="善于推理",
        playable=True,
        description="善于推理",
        abilities=["观察"],
        initial_location="镇口茶摊",
        starting_inventory=[],
        mode="both",
    )
    db.add(character)
    db.add(
        WorldCharacter(
            world_id=world.id,
            name="茶摊老板老孙",
            personality="谨慎",
            secret="知道镇上的流言",
            knowledge=[],
            schedule={},
            initial_location="镇口茶摊",
            playable=False,
        )
    )
    await db.commit()

    service = GameService(FakeOpeningOrchestrator())

    async for _ in service.start_game(db, user.id, world.id, character.id, "script", None, None):
        pass

    result = await db.execute(select(Message).order_by(Message.created_at.asc(), Message.id.asc()))
    messages = result.scalars().all()

    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].content == "浓雾从镇口漫过来。"
