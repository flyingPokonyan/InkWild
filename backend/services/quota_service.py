"""Daily creation quota service for workshop usage."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.quota import UserCreationQuota


class QuotaExceeded(Exception):
    def __init__(self, kind: str, used: int, limit: int):
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(f"{kind} quota exceeded: {used}/{limit}")


async def _consume(db: AsyncSession, user_id: str, field: str, daily_limit: int | None) -> int:
    """Consume 1 quota unit. Returns remaining (or -1 if unlimited). Raises QuotaExceeded if over limit."""
    today = date.today()

    existing = (await db.execute(
        select(UserCreationQuota).where(
            UserCreationQuota.user_id == user_id,
            UserCreationQuota.quota_date == today,
        )
    )).scalar_one_or_none()

    if existing is None:
        existing = UserCreationQuota(user_id=user_id, quota_date=today, **{field: 1})
        db.add(existing)
    else:
        setattr(existing, field, getattr(existing, field) + 1)

    await db.commit()
    new_count = getattr(existing, field)

    if daily_limit is None:
        return -1
    if new_count > daily_limit:
        raise QuotaExceeded(field, new_count, daily_limit)
    return daily_limit - new_count


async def consume_world_generation_quota(db: AsyncSession, user_id: str, daily_limit: int | None) -> int:
    """Consume 1 world generation quota. Returns remaining slots, or -1 if unlimited."""
    return await _consume(db, user_id, "world_generations", daily_limit)


async def consume_script_generation_quota(db: AsyncSession, user_id: str, daily_limit: int | None) -> int:
    """Consume 1 script generation quota. Returns remaining slots, or -1 if unlimited."""
    return await _consume(db, user_id, "script_generations", daily_limit)
