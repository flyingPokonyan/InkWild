import pytest
from sqlalchemy import select

from models.user import AuthIdentity, User
from services.oauth_service import normalize_profile, upsert_oauth_identity
from utils import utcnow


@pytest.mark.asyncio
async def test_new_oauth_user_created_with_profile(db):
    profile = {
        "provider_user_id": "g-123",
        "email": "new@ex.com",
        "email_verified": True,
        "name": "Neo",
        "avatar": "http://a/x.png",
    }
    user = await upsert_oauth_identity(db, "google", profile)
    assert user.nickname == "Neo"
    assert user.avatar_url == "http://a/x.png"
    ident = (await db.execute(select(AuthIdentity).where(AuthIdentity.provider == "google"))).scalar_one()
    assert ident.verified_at is not None


@pytest.mark.asyncio
async def test_existing_identity_returns_same_user(db):
    profile = {"provider_user_id": "g-1", "email": "x@ex.com", "email_verified": True, "name": "X", "avatar": None}
    u1 = await upsert_oauth_identity(db, "google", profile)
    u2 = await upsert_oauth_identity(db, "google", profile)
    assert u1.id == u2.id
    rows = (await db.execute(select(AuthIdentity).where(AuthIdentity.provider == "google"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_oauth_merges_into_verified_email_account(db):
    u = User(status="active", nickname="pw")
    db.add(u)
    await db.flush()
    db.add(AuthIdentity(user_id=u.id, provider="password", provider_user_id="dup@ex.com",
                        email="dup@ex.com", verified_at=utcnow()))
    await db.commit()

    profile = {"provider_user_id": "g-9", "email": "dup@ex.com", "email_verified": True, "name": "G", "avatar": None}
    user = await upsert_oauth_identity(db, "google", profile)
    assert user.id == u.id  # merged onto existing verified-email account
    gid = (await db.execute(select(AuthIdentity).where(AuthIdentity.provider == "google"))).scalar_one()
    assert gid.user_id == u.id


@pytest.mark.asyncio
async def test_unverified_oauth_email_does_not_merge(db):
    u = User(status="active", nickname="pw")
    db.add(u)
    await db.flush()
    db.add(AuthIdentity(user_id=u.id, provider="password", provider_user_id="z@ex.com",
                        email="z@ex.com", verified_at=utcnow()))
    await db.commit()

    profile = {"provider_user_id": "ld-7", "email": "z@ex.com", "email_verified": False, "name": "L", "avatar": None}
    user = await upsert_oauth_identity(db, "linuxdo", profile)
    assert user.id != u.id  # unverified email → separate account


def test_normalize_profile_google_lowercases_email():
    p = normalize_profile("google", {"sub": "s", "email": "A@B.com", "email_verified": True, "name": "N", "picture": "u"})
    assert p["provider_user_id"] == "s"
    assert p["email"] == "a@b.com"
    assert p["email_verified"] is True
    assert p["avatar"] == "u"


def test_normalize_profile_linuxdo():
    p = normalize_profile("linuxdo", {"id": 42, "email": "x@y.com", "name": "Z", "avatar_url": "a", "email_verified": True})
    assert p["provider_user_id"] == "42"
    assert p["name"] == "Z"
    assert p["email"] == "x@y.com"
