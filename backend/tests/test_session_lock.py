from unittest.mock import AsyncMock

import pytest

from services.session_lock import SessionLock


@pytest.mark.asyncio
async def test_acquire_and_release():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock()

    lock = SessionLock(mock_redis)

    acquired = await lock.acquire("session-123")
    assert acquired is True
    mock_redis.set.assert_called_once_with("lock:session:session-123", "1", nx=True, ex=60)

    await lock.release("session-123")
    mock_redis.delete.assert_called_once_with("lock:session:session-123")


@pytest.mark.asyncio
async def test_acquire_fails_when_locked():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=False)

    lock = SessionLock(mock_redis)
    acquired = await lock.acquire("session-123")

    assert acquired is False
