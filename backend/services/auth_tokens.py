"""Redis-backed single-use tokens for email verification / password reset / oauth state.

Tokens auto-expire (TTL) and are deleted on first consume (single-use).
"""

from __future__ import annotations

import json
import secrets

import redis.asyncio as redis


def _key(purpose: str, token: str) -> str:
    return f"auth:{purpose}:{token}"


async def create_token(r: redis.Redis, purpose: str, payload: dict, ttl: int) -> str:
    """Generate a random token, store payload under it with TTL, return the token."""
    token = secrets.token_urlsafe(32)
    await r.set(_key(purpose, token), json.dumps(payload), ex=ttl)
    return token


async def consume_token(r: redis.Redis, purpose: str, token: str) -> dict | None:
    """Return the payload and delete it (single-use). None if missing/expired/wrong purpose."""
    if not token:
        return None
    key = _key(purpose, token)
    raw = await r.get(key)
    if raw is None:
        return None
    await r.delete(key)
    return json.loads(raw)


async def put_token(r: redis.Redis, purpose: str, token: str, payload: dict, ttl: int) -> None:
    """Store payload under a caller-supplied token (e.g. OAuth state string). Single-use via consume_token."""
    await r.set(_key(purpose, token), json.dumps(payload), ex=ttl)
