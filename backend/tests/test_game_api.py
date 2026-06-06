from datetime import datetime, timedelta, timezone

import pytest

from models.game import GameSession, Message
from models.user import User, WebSession
from models.world import World, WorldCharacter


def _future_expiry():
    return datetime.now(timezone.utc) + timedelta(days=30)


@pytest.mark.asyncio
async def test_game_detail_returns_state_and_messages(client, db):
    user = User(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", nickname="tester")
    db.add(user)
    await db.flush()
    web_session = WebSession(user_id=user.id, expires_at=_future_expiry())
    db.add(web_session)
    await db.flush()

    world = World(
        id="11111111-1111-1111-1111-111111111111",
        name="雾隐镇",
        description="测试世界",
        genre="悬疑",
        era="民国",
        difficulty=3,
        estimated_time="30分钟",
        cover_image="",
        base_setting="base",
        script_setting="secret",
        status="published",
        play_count=0,
    )
    character = WorldCharacter(
        id="22222222-2222-2222-2222-222222222222",
        world_id=world.id,
        name="外来调查员",
        personality="善于推理",
        playable=True,
        description="善于推理",
        abilities=["观察"],
        initial_location="镇口",
        starting_inventory=["笔记本"],
        mode="both",
    )
    session = GameSession(
        id="33333333-3333-3333-3333-333333333333",
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"current_location": "茶摊", "current_time": "第1天·下午"},
        rounds_played=1,
    )

    db.add_all(
        [
            world,
            character,
            session,
            Message(session_id=session.id, role="user", content="我去茶摊"),
            Message(session_id=session.id, role="assistant", content="你看见茶摊边有人低声交谈。"),
        ]
    )
    await db.commit()

    response = await client.get(
        f"/api/game/{session.id}/detail",
        cookies={"inkwild_session": web_session.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["session_id"] == session.id
    assert payload["data"]["world_name"] == "雾隐镇"
    assert payload["data"]["character_name"] == "外来调查员"
    assert payload["data"]["game_state"]["current_location"] == "茶摊"
    assert [message["role"] for message in payload["data"]["messages"]] == ["user", "assistant"]
    assert payload["data"]["messages"][1]["content"] == "你看见茶摊边有人低声交谈。"


@pytest.mark.asyncio
async def test_game_history_empty(client, db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()
    web_session = WebSession(user_id=user.id, expires_at=_future_expiry())
    db.add(web_session)
    await db.commit()

    response = await client.get(
        "/api/game/history",
        cookies={"inkwild_session": web_session.id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"] == []


@pytest.mark.asyncio
async def test_pause_nonexistent_game(client, db):
    user = User(nickname="tester")
    db.add(user)
    await db.flush()
    web_session = WebSession(user_id=user.id, expires_at=_future_expiry())
    db.add(web_session)
    await db.commit()

    response = await client.post(
        "/api/game/00000000-0000-0000-0000-000000000000/pause",
        cookies={"inkwild_session": web_session.id},
    )

    assert response.status_code in (400, 404, 500)
