import redis.asyncio as redis

from config import settings


class SessionLock:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def acquire(self, session_id: str, timeout: int | None = None) -> bool:
        timeout = timeout or settings.session_lock_timeout
        result = await self.redis.set(
            f"lock:session:{session_id}",
            "1",
            nx=True,
            ex=timeout,
        )
        return result is True

    async def release(self, session_id: str):
        await self.redis.delete(f"lock:session:{session_id}")
