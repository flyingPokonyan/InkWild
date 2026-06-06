import pytest

from services.auth_tokens import create_token, consume_token, put_token


@pytest.mark.asyncio
async def test_create_and_consume_single_use(fake_redis):
    token = await create_token(fake_redis, "verify", {"user_id": "u1", "identity_id": "i1"}, ttl=60)
    assert isinstance(token, str) and len(token) > 20
    payload = await consume_token(fake_redis, "verify", token)
    assert payload == {"user_id": "u1", "identity_id": "i1"}
    # second consume returns None (single-use)
    assert await consume_token(fake_redis, "verify", token) is None


@pytest.mark.asyncio
async def test_wrong_purpose_is_namespaced(fake_redis):
    token = await create_token(fake_redis, "verify", {"x": 1}, ttl=60)
    assert await consume_token(fake_redis, "reset", token) is None
    # original purpose still works
    assert await consume_token(fake_redis, "verify", token) == {"x": 1}


@pytest.mark.asyncio
async def test_consume_missing_and_empty(fake_redis):
    assert await consume_token(fake_redis, "verify", "nope") is None
    assert await consume_token(fake_redis, "verify", "") is None


@pytest.mark.asyncio
async def test_put_token_with_caller_supplied_key(fake_redis):
    await put_token(fake_redis, "oauth_state", "state-abc", {"provider": "google", "next": "/"}, ttl=60)
    assert await consume_token(fake_redis, "oauth_state", "state-abc") == {"provider": "google", "next": "/"}
    assert await consume_token(fake_redis, "oauth_state", "state-abc") is None
