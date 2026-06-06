from dataclasses import dataclass

import redis.asyncio as redis


_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])

local bucket = redis.call("HMGET", key, "tokens", "updated_at")
local tokens = tonumber(bucket[1])
local updated_at = tonumber(bucket[2])

if tokens == nil then
  tokens = limit
  updated_at = now_ms
end

local refill_per_ms = limit / (window_seconds * 1000)
tokens = math.min(limit, tokens + ((now_ms - updated_at) * refill_per_ms))

local allowed = 0
local retry_after = 0
if tokens >= 1 then
  allowed = 1
  tokens = tokens - 1
else
  retry_after = math.ceil((1 - tokens) / refill_per_ms / 1000)
end

redis.call("HSET", key, "tokens", tokens, "updated_at", now_ms)
redis.call("EXPIRE", key, math.ceil(window_seconds * 2))

return {allowed, math.floor(tokens), retry_after}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    remaining_tokens: int


class RedisTokenBucketRateLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def allow(self, user_id: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        now_ms = await self._redis_time_ms()
        key = f"rate:game_action:{user_id}"
        allowed, remaining_tokens, retry_after = await self.redis.eval(
            _TOKEN_BUCKET_LUA,
            1,
            key,
            max(limit, 1),
            max(window_seconds, 1),
            now_ms,
        )
        return RateLimitResult(
            allowed=bool(int(allowed)),
            remaining_tokens=max(int(remaining_tokens), 0),
            retry_after_seconds=max(int(retry_after), 0),
        )

    async def _redis_time_ms(self) -> int:
        seconds, microseconds = await self.redis.time()
        return int(seconds) * 1000 + int(microseconds) // 1000
