import pytest

from config import settings


async def _verify_token(fake_redis) -> str:
    keys = await fake_redis.keys("auth:verify:*")
    assert keys
    return keys[0].split(":")[-1]


@pytest.mark.asyncio
async def test_register_verify_login_flow(auth_client, fake_redis):
    # register
    r = await auth_client.post("/api/auth/register", json={"email": "New@Ex.com", "password": "hunter2pw"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["pending_verification"] is True
    assert body["data"]["email"] == "new@ex.com"

    # unverified login is blocked
    r2 = await auth_client.post("/api/auth/password/login", json={"email": "new@ex.com", "password": "hunter2pw"})
    assert r2.status_code == 403
    assert r2.json()["code"] == 40302

    # verify via token from redis
    token = await _verify_token(fake_redis)
    r3 = await auth_client.post("/api/auth/verify-email", json={"token": token})
    assert r3.status_code == 200
    assert settings.auth_cookie_name in r3.cookies
    assert r3.json()["data"]["identities"][0]["email"] == "new@ex.com"

    # now login works
    r4 = await auth_client.post("/api/auth/password/login", json={"email": "new@ex.com", "password": "hunter2pw"})
    assert r4.status_code == 200


@pytest.mark.asyncio
async def test_register_duplicate_verified_returns_409(auth_client, fake_redis):
    await auth_client.post("/api/auth/register", json={"email": "dup@ex.com", "password": "hunter2pw"})
    token = await _verify_token(fake_redis)
    await auth_client.post("/api/auth/verify-email", json={"token": token})
    r = await auth_client.post("/api/auth/register", json={"email": "dup@ex.com", "password": "another1pw"})
    assert r.status_code == 409
    assert r.json()["code"] == 40901


@pytest.mark.asyncio
async def test_register_invalid_email_422(auth_client):
    r = await auth_client.post("/api/auth/register", json={"email": "not-an-email", "password": "hunter2pw"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_verify_bad_token_400(auth_client):
    r = await auth_client.post("/api/auth/verify-email", json={"token": "garbage"})
    assert r.status_code == 400
    assert r.json()["code"] == 40010
