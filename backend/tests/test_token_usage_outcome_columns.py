"""Phase 9 tests: token_usage.outcome and retry_count columns persist correctly."""
import pytest
import uuid

from sqlalchemy import select
from models.game import TokenUsage, GameSession
from models.user import User
from models.world import World, WorldCharacter


async def _make_session(db) -> str:
    user = User(nickname="t")
    db.add(user)
    await db.flush()
    world = World(
        name="w", description="", genre="", era="", difficulty=3,
        estimated_time="", base_setting="x", locations_data=[], status="published",
        created_by_user_id=user.id,
    )
    db.add(world)
    await db.flush()
    char = WorldCharacter(world_id=world.id, name="A", playable=True)
    db.add(char)
    await db.flush()
    sess = GameSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        world_id=world.id,
        character_id=char.id,
        mode="script",
        status="ongoing",
        game_state={},
        rounds_played=0,
        started_at=__import__("datetime").datetime.utcnow(),
        last_played_at=__import__("datetime").datetime.utcnow(),
    )
    db.add(sess)
    await db.commit()
    return sess.id


@pytest.mark.asyncio
async def test_token_usage_outcome_defaults_to_success(db):
    sess_id = await _make_session(db)
    row = TokenUsage(
        session_id=sess_id,
        purpose="game",
        provider="deepseek",
        model="deepseek-v4-pro",
        input_tokens=100,
        output_tokens=50,
    )
    db.add(row)
    await db.commit()
    fetched = (await db.execute(select(TokenUsage).where(TokenUsage.id == row.id))).scalar_one()
    assert fetched.outcome == "success"
    assert fetched.retry_count == 0


@pytest.mark.asyncio
async def test_token_usage_outcome_parse_failure_persists(db):
    sess_id = await _make_session(db)
    row = TokenUsage(
        session_id=sess_id,
        purpose="game",
        provider="deepseek",
        model="deepseek-v4-pro",
        input_tokens=100,
        output_tokens=50,
        outcome="parse_failure",
        retry_count=3,
    )
    db.add(row)
    await db.commit()
    fetched = (await db.execute(select(TokenUsage).where(TokenUsage.id == row.id))).scalar_one()
    assert fetched.outcome == "parse_failure"
    assert fetched.retry_count == 3


@pytest.mark.asyncio
async def test_token_usage_outcome_retried_success(db):
    sess_id = await _make_session(db)
    row = TokenUsage(
        session_id=sess_id,
        purpose="game",
        provider="deepseek",
        model="deepseek-v4-pro",
        input_tokens=100,
        output_tokens=50,
        outcome="retried_success",
        retry_count=1,
    )
    db.add(row)
    await db.commit()
    fetched = (await db.execute(select(TokenUsage).where(TokenUsage.id == row.id))).scalar_one()
    assert fetched.outcome == "retried_success"
    assert fetched.retry_count == 1
