import pytest
from models.user import User
from services.quota_service import (
    QuotaExceeded,
    consume_script_generation_quota,
    consume_world_generation_quota,
)


@pytest.fixture
async def sample_user(db):
    user = User(nickname="test_user")
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_consume_world_quota_first_time(db, sample_user):
    remaining = await consume_world_generation_quota(db, sample_user.id, daily_limit=2)
    assert remaining == 1


@pytest.mark.asyncio
async def test_consume_world_quota_exhausts(db, sample_user):
    await consume_world_generation_quota(db, sample_user.id, daily_limit=2)
    await consume_world_generation_quota(db, sample_user.id, daily_limit=2)
    with pytest.raises(QuotaExceeded):
        await consume_world_generation_quota(db, sample_user.id, daily_limit=2)


@pytest.mark.asyncio
async def test_admin_bypass_unlimited(db, sample_user):
    # daily_limit=None means unlimited
    for _ in range(5):
        result = await consume_world_generation_quota(db, sample_user.id, daily_limit=None)
        assert result == -1
