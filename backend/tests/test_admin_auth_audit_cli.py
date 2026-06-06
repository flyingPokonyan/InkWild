import pytest

from cli import create_admin
from models.audit_log import AdminAuditLog
from models.user import AuthIdentity, User
from services.audit_service import record_admin_action
from services.auth_service import verify_password


@pytest.mark.asyncio
async def test_record_admin_action_persists_audit_log(db):
    admin = User(nickname="admin", is_admin=True)
    db.add(admin)
    await db.flush()

    log = await record_admin_action(
        db,
        admin_user=admin,
        action="world.publish",
        resource_type="world",
        resource_id="world-1",
        payload={"source": "test"},
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    await db.commit()

    saved = await db.get(AdminAuditLog, log.id)
    assert saved is not None
    assert saved.admin_user_id == admin.id
    assert saved.action == "world.publish"
    assert saved.payload == {"source": "test"}


@pytest.mark.asyncio
async def test_create_admin_cli_creates_password_admin_user(test_session_factory, monkeypatch):
    monkeypatch.setattr(create_admin, "async_session", test_session_factory)

    user = await create_admin.create_or_promote_admin(" Admin@Example.COM ", "secret-pass")

    async with test_session_factory() as db:
        saved = await db.get(User, user.id)
        assert saved is not None
        assert saved.is_admin is True
        identity = (
            await db.execute(
                create_admin.select(AuthIdentity).where(
                    AuthIdentity.provider == "password",
                    AuthIdentity.provider_user_id == "admin@example.com",
                )
            )
        ).scalar_one()
        assert verify_password("secret-pass", identity.credential_hash or "")


@pytest.mark.asyncio
async def test_create_admin_cli_promotes_existing_password_user(test_session_factory, monkeypatch):
    monkeypatch.setattr(create_admin, "async_session", test_session_factory)

    async with test_session_factory() as db:
        user = User(nickname="existing", is_admin=False)
        db.add(user)
        await db.flush()
        db.add(
            AuthIdentity(
                user_id=user.id,
                provider="password",
                provider_user_id="existing@example.com",
                credential_hash="hash",
                email="existing@example.com",
            )
        )
        await db.commit()
        user_id = user.id

    promoted = await create_admin.create_or_promote_admin("existing@example.com", None)

    async with test_session_factory() as db:
        saved = await db.get(User, user_id)
        assert promoted.id == user_id
        assert saved is not None
        assert saved.is_admin is True
