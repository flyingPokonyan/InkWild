import pytest
from sqlalchemy import select

from engine.state_manager import GameState
from models.game import GameSession, Message
from models.user import User
from models.world import Character, World
from services.game_service import GameService


class UnexpectedOrchestrator:
    """退场命令必须绕过 orchestrator（不跑导演/NPC 流水线），只用其 ending_summary
    槽位生成落幕白。给一个 None router，让 generate_ending_summary 走自身兜底。"""

    ending_summary_llm_router = None

    async def process_action(self, *args, **kwargs):
        raise AssertionError("withdraw command should bypass orchestrator")
        yield {}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["script", "free"])
async def test_withdraw_command_ends_session_with_sendoff(db, mode):
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
            "__inkwild_withdraw__",
        )
    ]

    assert [event["type"] for event in events] == ["narrative", "state_update", "ending", "done"]
    assert events[2]["ending_type"] == "withdrawn"
    assert events[2]["title"] == "搁笔"
    # 落幕白：summary 必带非空 ending_narrative（即便 LLM 失败也有静态兜底）
    assert isinstance(events[2]["summary"]["ending_narrative"], str)
    assert events[2]["summary"]["ending_narrative"].strip()

    await db.refresh(session)
    assert session.status == "ended"
    assert session.ending_type == "withdrawn"
    # 退场不推进世界：回合数与 game_state 原样不动
    assert session.rounds_played == 4
    assert session.game_state == initial_state.to_dict()

    # 哨兵串不入库（save_messages=False），历史里不留 "__inkwild_withdraw__"
    messages = (
        await db.execute(select(Message).where(Message.session_id == session.id))
    ).scalars().all()
    assert messages == []


@pytest.mark.asyncio
async def test_withdraw_works_even_when_cost_capped(db):
    """费用封顶的 session 也必须能退场（拦截在 cost gate 之前）。"""
    user = User(nickname="封顶玩家")
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

    state = GameState(current_time="第3天·清晨", current_location="钟楼", round_number=20)
    session = GameSession(
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state=state.to_dict(),
        rounds_played=20,
    )
    db.add(session)
    await db.commit()

    service = GameService(UnexpectedOrchestrator())

    types = [
        event["type"]
        async for event in service.process_action(
            db, user.id, session.id, "__inkwild_withdraw__"
        )
    ]

    # 没有被 cost gate 的 cap_reached 截断，正常走到 ending
    assert "ending" in types
    assert "cap_reached" not in types
    await db.refresh(session)
    assert session.status == "ended"
    assert session.ending_type == "withdrawn"
