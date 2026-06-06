from datetime import timedelta

import pytest

from config import settings
from middleware.error_handler import AppError
from models.user import AuthIdentity, User, WebSession
from services.auth_service import AuthService, hash_password
from utils import utcnow


async def _create_password_user(db, email: str, password: str) -> User:
    user = User(nickname="Dev User")
    db.add(user)
    await db.flush()
    db.add(
        AuthIdentity(
            user_id=user.id,
            provider="password",
            provider_user_id=email.lower(),
            credential_hash=hash_password(password),
            email=email.lower(),
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_password_login_creates_web_session(db):
    user = await _create_password_user(db, "pokonyan1666@gmail.com", "secret-pass")

    service = AuthService()
    session = await service.login_with_password(db, "pokonyan1666@gmail.com", "secret-pass")

    assert isinstance(session, WebSession)
    assert session.user_id == user.id
    assert session.expires_at > session.created_at


@pytest.mark.asyncio
async def test_password_login_rejects_invalid_password(db):
    await _create_password_user(db, "pokonyan1666@gmail.com", "secret-pass")

    service = AuthService()

    with pytest.raises(AppError) as exc_info:
        await service.login_with_password(db, "pokonyan1666@gmail.com", "wrong-pass")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_user_by_session_id_returns_none_for_expired_session(db):
    user = await _create_password_user(db, "pokonyan1666@gmail.com", "secret-pass")
    expired_session = WebSession(
        user_id=user.id,
        expires_at=utcnow() - timedelta(days=1),
    )
    db.add(expired_session)
    await db.commit()

    service = AuthService()

    assert await service.get_user_by_session_id(db, expired_session.id) is None


@pytest.mark.asyncio
async def test_logout_removes_active_session(db):
    user = await _create_password_user(db, "pokonyan1666@gmail.com", "secret-pass")
    session = WebSession(
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(session)
    await db.commit()

    service = AuthService()
    await service.logout(db, session.id)

    assert await db.get(WebSession, session.id) is None


@pytest.mark.asyncio
async def test_login_dev_user_requires_flag(db, monkeypatch):
    monkeypatch.setattr(settings, "enable_dev_auth", False)

    service = AuthService()

    with pytest.raises(AppError) as exc_info:
        await service.login_dev_user(db)

    assert exc_info.value.status_code == 404
