from datetime import timedelta

import pytest

from api.credits import _parse_category_filter
from config import settings
from models.credit import CreditLedger
from models.draft import WorldDraft
from models.game import GameSession
from models.generation_task import GenerationTask
from models.script import Script
from models.user import User, WebSession
from models.world import World, WorldCharacter
from utils import utcnow


@pytest.mark.no_db
def test_parse_category_filter_supports_grouped_categories():
    assert _parse_category_filter(None) is None
    assert _parse_category_filter("") is None
    assert _parse_category_filter("play") == ["play"]
    assert _parse_category_filter("creation,image") == ["creation", "image"]
    assert _parse_category_filter("grant, adjust") == ["grant", "adjust"]
    assert _parse_category_filter("unknown") == []


async def test_transactions_filter_accepts_grouped_categories(client, db):
    user = User(nickname="ledger")
    db.add(user)
    await db.flush()

    web_session = WebSession(
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=1),
    )
    db.add(web_session)

    now = utcnow()
    db.add_all(
        [
            CreditLedger(
                user_id=user.id,
                delta_units=-10_000,
                balance_after_units=490_000,
                kind="debit_game",
                category="play",
                created_at=now,
            ),
            CreditLedger(
                user_id=user.id,
                delta_units=-20_000,
                balance_after_units=470_000,
                kind="debit_world_gen",
                category="creation",
                created_at=now - timedelta(minutes=1),
            ),
            CreditLedger(
                user_id=user.id,
                delta_units=-30_000,
                balance_after_units=440_000,
                kind="debit_image_gen",
                category="image",
                created_at=now - timedelta(minutes=2),
            ),
            CreditLedger(
                user_id=user.id,
                delta_units=50_000,
                balance_after_units=500_000,
                kind="admin_adjust",
                category="adjust",
                created_at=now - timedelta(minutes=3),
            ),
        ]
    )
    await db.commit()

    client.cookies.set(settings.auth_cookie_name, web_session.id)
    response = await client.get("/api/credits/transactions?category=creation,image")

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["category"] for item in items] == ["creation", "image"]


async def test_transactions_enriches_ref_context(client, db):
    """Debit rows resolve to world/script names + per-run turn ordinal; rows with
    a missing or ref-less source degrade gracefully to null context."""
    user = User(nickname="ledger")
    db.add(user)
    await db.flush()
    web_session = WebSession(user_id=user.id, expires_at=utcnow() + timedelta(days=1))
    db.add(web_session)

    world = World(
        name="紫禁深宫",
        description="d",
        genre="g",
        era="e",
        difficulty=3,
        estimated_time="30",
        base_setting="b",
    )
    db.add(world)
    await db.flush()
    char = WorldCharacter(world_id=world.id, name="甄嬛")
    script = Script(world_id=world.id, name="甄嬛传", description="d")
    db.add_all([char, script])
    await db.flush()

    script_session = GameSession(
        user_id=user.id, world_id=world.id, character_id=char.id, script_id=script.id, mode="script"
    )
    free_session = GameSession(
        user_id=user.id, world_id=world.id, character_id=char.id, mode="free"
    )
    db.add_all([script_session, free_session])
    await db.flush()

    draft = WorldDraft(payload={"name": "测试世界草稿"}, created_by_user_id=user.id)
    db.add(draft)
    await db.flush()
    task = GenerationTask(
        kind="world", draft_type="world_draft", draft_id=draft.id, created_by_user_id=user.id
    )
    db.add(task)
    await db.flush()

    now = utcnow()
    rows = {
        "play1": CreditLedger(
            user_id=user.id, delta_units=-10_000, balance_after_units=490_000,
            kind="debit_game", category="play", ref_type="session", ref_id=script_session.id,
            created_at=now - timedelta(minutes=5),
        ),
        "play2": CreditLedger(
            user_id=user.id, delta_units=-10_000, balance_after_units=480_000,
            kind="debit_game", category="play", ref_type="session", ref_id=script_session.id,
            created_at=now - timedelta(minutes=4),
        ),
        "free": CreditLedger(
            user_id=user.id, delta_units=-10_000, balance_after_units=470_000,
            kind="debit_game", category="play", ref_type="session", ref_id=free_session.id,
            created_at=now - timedelta(minutes=3),
        ),
        "gen": CreditLedger(
            user_id=user.id, delta_units=-20_000, balance_after_units=450_000,
            kind="debit_world_gen", category="creation", ref_type="task", ref_id=task.id,
            created_at=now - timedelta(minutes=2),
        ),
        "grant": CreditLedger(
            user_id=user.id, delta_units=50_000, balance_after_units=500_000,
            kind="admin_adjust", category="adjust",
            created_at=now - timedelta(minutes=1),
        ),
        "ghost": CreditLedger(
            user_id=user.id, delta_units=-10_000, balance_after_units=440_000,
            kind="debit_game", category="play", ref_type="session", ref_id="dead-session-id",
            created_at=now,
        ),
    }
    db.add_all(list(rows.values()))
    await db.commit()

    client.cookies.set(settings.auth_cookie_name, web_session.id)
    response = await client.get("/api/credits/transactions")
    assert response.status_code == 200
    by_id = {it["id"]: it for it in response.json()["data"]["items"]}

    p1 = by_id[rows["play1"].id]
    assert (p1["ref_title"], p1["ref_subtitle"], p1["ref_mode"], p1["ref_turn"]) == (
        "紫禁深宫", "甄嬛传", "script", 1,
    )
    assert by_id[rows["play2"].id]["ref_turn"] == 2

    fr = by_id[rows["free"].id]
    assert (fr["ref_title"], fr["ref_subtitle"], fr["ref_mode"], fr["ref_turn"]) == (
        "紫禁深宫", None, "free", 1,
    )

    assert by_id[rows["gen"].id]["ref_title"] == "测试世界草稿"
    assert by_id[rows["grant"].id]["ref_title"] is None
    assert by_id[rows["ghost"].id]["ref_title"] is None


async def test_transactions_filter_returns_empty_for_unknown_category(client, db):
    user = User(nickname="ledger")
    db.add(user)
    await db.flush()

    web_session = WebSession(
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=1),
    )
    db.add(web_session)
    db.add(
        CreditLedger(
            user_id=user.id,
            delta_units=-10_000,
            balance_after_units=490_000,
            kind="debit_game",
            category="play",
        )
    )
    await db.commit()

    client.cookies.set(settings.auth_cookie_name, web_session.id)
    response = await client.get("/api/credits/transactions?category=unknown")

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
