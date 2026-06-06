import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_worlds_table_has_v2_fields(async_engine):
    async with async_engine.connect() as conn:
        cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("worlds")})
    assert "lore_pack" in cols
    assert "shared_events" in cols
    assert "events_data" in cols


@pytest.mark.asyncio
async def test_generation_tasks_has_intermediate_state(async_engine):
    async with async_engine.connect() as conn:
        cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("generation_tasks")})
    assert "intermediate_state" in cols
