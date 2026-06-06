"""Light coverage for created_by_user_id ownership fields (Task B2)."""
import pytest
from sqlalchemy import select

from models.draft import WorldDraft
from models.generation_task import GenerationTask
from models.user import User
from models.world import World


@pytest.mark.asyncio
async def test_world_draft_has_creator(db):
    user = User(nickname="creator", is_admin=False)
    db.add(user)
    await db.flush()

    draft = WorldDraft(payload={}, created_by_user_id=user.id)
    db.add(draft)
    await db.commit()

    row = (await db.execute(select(WorldDraft).where(WorldDraft.id == draft.id))).scalar_one()
    assert row.created_by_user_id == user.id


@pytest.mark.asyncio
async def test_world_creator_nullable(db):
    world = World(
        name="Official",
        description="seed",
        genre="mystery",
        era="modern",
        difficulty=3,
        estimated_time="30",
        base_setting="seed",
    )
    db.add(world)
    await db.commit()
    assert world.created_by_user_id is None
