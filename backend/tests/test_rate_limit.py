from unittest.mock import AsyncMock

import pytest

from middleware.rate_limit import RedisTokenBucketRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_when_bucket_has_tokens():
    redis = AsyncMock()
    redis.time = AsyncMock(return_value=(1, 0))
    redis.eval = AsyncMock(return_value=[1, 29, 0])
    limiter = RedisTokenBucketRateLimiter(redis)

    result = await limiter.allow("user-1", limit=30, window_seconds=60)

    assert result.allowed is True
    assert result.retry_after_seconds == 0
    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limiter_returns_retry_after_when_bucket_is_empty():
    redis = AsyncMock()
    redis.time = AsyncMock(return_value=(1, 0))
    redis.eval = AsyncMock(return_value=[0, 0, 2])
    limiter = RedisTokenBucketRateLimiter(redis)

    result = await limiter.allow("user-1", limit=30, window_seconds=60)

    assert result.allowed is False
    assert result.retry_after_seconds == 2
