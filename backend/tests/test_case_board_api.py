from datetime import datetime, timedelta, timezone

import pytest

from models.case_board_history import CaseBoardHistory
from models.game import GameSession
from models.user import User, WebSession
from models.world import World, WorldCharacter


def _future_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=30)


@pytest.mark.asyncio
async def test_case_board_returns_current_and_history(client, db):
    user = User(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", nickname="owner")
    db.add(user)
    await db.flush()
    web_session = WebSession(user_id=user.id, expires_at=_future_expiry())
    db.add(web_session)
    await db.flush()

    world = World(
        id="11111111-1111-1111-1111-111111111111",
        name="Fog Town",
        description="Test world",
        genre="Mystery",
        era="Modern",
        difficulty=3,
        estimated_time="30 minutes",
        cover_image="",
        base_setting="base",
        script_setting="secret",
        status="published",
        play_count=0,
    )
    character = WorldCharacter(
        id="22222222-2222-2222-2222-222222222222",
        world_id=world.id,
        name="Detective",
        personality="Careful",
        playable=True,
        description="Careful",
        abilities=["Observe"],
        initial_location="Station",
        starting_inventory=["Notebook"],
        mode="both",
    )
    current_board = {
        "entities": [{"id": "npc_1", "label": "Witness"}],
        "edges": [],
    }
    session = GameSession(
        id="33333333-3333-3333-3333-333333333333",
        user_id=user.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"case_board": current_board, "current_location": "Station"},
        rounds_played=2,
    )
    db.add_all(
        [
            world,
            character,
            session,
            CaseBoardHistory(
                session_id=session.id,
                round_number=1,
                op_type="add_entity",
                path=["entities", "npc_1"],
                payload={"id": "npc_1", "label": "Witness"},
                before=None,
                after={"id": "npc_1", "label": "Witness"},
                reason="new witness",
            ),
            CaseBoardHistory(
                session_id=session.id,
                round_number=2,
                op_type="update_entity",
                path=["entities", "npc_1", "label"],
                payload={"label": "Key Witness"},
                before={"label": "Witness"},
                after={"label": "Key Witness"},
            ),
        ]
    )
    await db.commit()

    response = await client.get(
        f"/api/game/{session.id}/case-board",
        cookies={"inkwild_session": web_session.id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["current"] == current_board
    assert [item["op_type"] for item in body["data"]["history"]] == ["add_entity", "update_entity"]
    assert body["data"]["history"][0]["path"] == ["entities", "npc_1"]
    assert body["data"]["history"][0]["reason"] == "new witness"
    assert "created_at" in body["data"]["history"][0]


@pytest.mark.asyncio
async def test_case_board_rejects_non_owner(client, db):
    owner = User(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", nickname="owner")
    other = User(id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", nickname="other")
    db.add_all([owner, other])
    await db.flush()
    other_web_session = WebSession(user_id=other.id, expires_at=_future_expiry())
    db.add(other_web_session)
    await db.flush()

    world = World(
        id="11111111-1111-1111-1111-111111111111",
        name="Fog Town",
        description="Test world",
        genre="Mystery",
        era="Modern",
        difficulty=3,
        estimated_time="30 minutes",
        cover_image="",
        base_setting="base",
        script_setting="secret",
        status="published",
        play_count=0,
    )
    character = WorldCharacter(
        id="22222222-2222-2222-2222-222222222222",
        world_id=world.id,
        name="Detective",
        personality="Careful",
        playable=True,
        description="Careful",
        abilities=["Observe"],
        initial_location="Station",
        starting_inventory=["Notebook"],
        mode="both",
    )
    session = GameSession(
        id="33333333-3333-3333-3333-333333333333",
        user_id=owner.id,
        world_id=world.id,
        character_id=character.id,
        mode="script",
        status="playing",
        game_state={"case_board": {"entities": [], "edges": []}},
        rounds_played=1,
    )
    db.add_all([world, character, session])
    await db.commit()

    response = await client.get(
        f"/api/game/{session.id}/case-board",
        cookies={"inkwild_session": other_web_session.id},
    )

    assert response.status_code == 404
