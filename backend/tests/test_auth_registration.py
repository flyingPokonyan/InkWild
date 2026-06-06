import pytest
from sqlalchemy import select

from middleware.error_handler import AppError
from models.user import AuthIdentity, User
from services.auth_service import AuthService, _find_password_identity
from utils import utcnow


async def _verify_token_for(fake_redis) -> str:
    keys = await fake_redis.keys("auth:verify:*")
    assert keys, "no verify token stored"
    return keys[0].split(":")[-1]


@pytest.mark.asyncio
async def test_register_creates_unverified_identity_no_session(db, fake_redis):
    svc = AuthService()
    identity = await svc.register_with_password(db, fake_redis, email="A@Ex.com", password="hunter2pw")
    assert identity.provider == "password"
    assert identity.provider_user_id == "a@ex.com"  # normalized
    assert identity.verified_at is None
    # user created, but no web_session issued (must verify first)
    user = await db.get(User, identity.user_id)
    assert user is not None and user.status == "active"


@pytest.mark.asyncio
async def test_reregister_unverified_is_idempotent(db, fake_redis):
    svc = AuthService()
    i1 = await svc.register_with_password(db, fake_redis, email="b@ex.com", password="firstpass1")
    i2 = await svc.register_with_password(db, fake_redis, email="b@ex.com", password="secondpass2")
    assert i1.id == i2.id  # same identity, no duplicate
    rows = (await db.execute(select(AuthIdentity).where(AuthIdentity.provider_user_id == "b@ex.com"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_register_already_verified_rejected(db, fake_redis):
    svc = AuthService()
    await svc.register_with_password(db, fake_redis, email="c@ex.com", password="passpass1")
    token = await _verify_token_for(fake_redis)
    await svc.verify_email(db, fake_redis, token)
    with pytest.raises(AppError) as exc:
        await svc.register_with_password(db, fake_redis, email="c@ex.com", password="passpass2")
    assert exc.value.code == 40901


@pytest.mark.asyncio
async def test_short_password_rejected(db, fake_redis):
    svc = AuthService()
    with pytest.raises(AppError) as exc:
        await svc.register_with_password(db, fake_redis, email="d@ex.com", password="short")
    assert exc.value.code == 40001


@pytest.mark.asyncio
async def test_verify_email_sets_verified_and_returns_session(db, fake_redis):
    svc = AuthService()
    identity = await svc.register_with_password(db, fake_redis, email="e@ex.com", password="passpass1")
    token = await _verify_token_for(fake_redis)
    session = await svc.verify_email(db, fake_redis, token)
    assert session.user_id == identity.user_id
    refreshed = await _find_password_identity(db, "e@ex.com")
    assert refreshed.verified_at is not None
    # token is single-use
    with pytest.raises(AppError):
        await svc.verify_email(db, fake_redis, token)


@pytest.mark.asyncio
async def test_login_gate_blocks_unverified(db, fake_redis):
    svc = AuthService()
    await svc.register_with_password(db, fake_redis, email="f@ex.com", password="passpass1")
    with pytest.raises(AppError) as exc:
        await svc.login_with_password(db, "f@ex.com", "passpass1")
    assert exc.value.code == 40302  # 请先验证邮箱


@pytest.mark.asyncio
async def test_resolve_merges_by_verified_email(db, fake_redis):
    # user A: verified google identity for x@ex.com
    user_a = User(status="active", nickname="A")
    db.add(user_a)
    await db.flush()
    id_a = AuthIdentity(user_id=user_a.id, provider="google", provider_user_id="g1",
                        email="x@ex.com", verified_at=utcnow())
    db.add(id_a)
    # user B: password identity for same email, just became verified
    user_b = User(status="active", nickname="B")
    db.add(user_b)
    await db.flush()
    id_b = AuthIdentity(user_id=user_b.id, provider="password", provider_user_id="x@ex.com",
                        email="x@ex.com", verified_at=utcnow())
    db.add(id_b)
    await db.commit()

    svc = AuthService()
    resolved = await svc.resolve_account_by_verified_email(db, "x@ex.com", id_b)
    await db.commit()
    assert resolved.id == user_a.id          # merged onto A
    assert id_b.user_id == user_a.id         # B's identity re-homed
    assert await db.get(User, user_b.id) is None  # orphan B deleted
