import pytest


async def _token(fake_redis, purpose: str) -> str:
    keys = await fake_redis.keys(f"auth:{purpose}:*")
    assert keys, f"no {purpose} token"
    return keys[0].split(":")[-1]


@pytest.mark.asyncio
async def test_forgot_nonexistent_is_silent(auth_client, fake_redis):
    r = await auth_client.post("/api/auth/password/forgot", json={"email": "nobody@ex.com"})
    assert r.status_code == 200
    assert await fake_redis.keys("auth:reset:*") == []


@pytest.mark.asyncio
async def test_forgot_and_reset_flow(auth_client, fake_redis):
    await auth_client.post("/api/auth/register", json={"email": "r@ex.com", "password": "oldpass12"})
    await auth_client.post("/api/auth/verify-email", json={"token": await _token(fake_redis, "verify")})
    assert (await auth_client.get("/api/auth/me")).json()["data"] is not None

    await auth_client.post("/api/auth/password/forgot", json={"email": "r@ex.com"})
    rr = await auth_client.post(
        "/api/auth/password/reset",
        json={"token": await _token(fake_redis, "reset"), "new_password": "newpass123"},
    )
    assert rr.status_code == 200

    # old session invalidated
    assert (await auth_client.get("/api/auth/me")).json()["data"] is None
    # old password fails, new password works
    bad = await auth_client.post("/api/auth/password/login", json={"email": "r@ex.com", "password": "oldpass12"})
    assert bad.status_code == 401
    good = await auth_client.post("/api/auth/password/login", json={"email": "r@ex.com", "password": "newpass123"})
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_reset_bad_token_400(auth_client):
    r = await auth_client.post(
        "/api/auth/password/reset", json={"token": "garbage", "new_password": "newpass123"}
    )
    assert r.status_code == 400
    assert r.json()["code"] == 40010
