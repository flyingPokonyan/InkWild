from datetime import datetime, timedelta, timezone

import pytest
import fakeredis.aioredis as _fakeredis
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database import Base
from dependencies import get_db, get_redis
from main import app
from models.user import User, WebSession

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"
_TEST_ENGINE = create_async_engine(TEST_DB_URL)
_TEST_SESSION_FACTORY = async_sessionmaker(_TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_db(request):
    if request.node.get_closest_marker("no_db"):
        yield
        return

    async with _TEST_ENGINE.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with _TEST_ENGINE.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with _TEST_SESSION_FACTORY() as session:
        yield session


async def override_get_redis():
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock()
    return mock


class _StubEvalRedis(_fakeredis.FakeRedis):
    """In-memory redis for auth tests. Real get/set/delete/ttl semantics; the
    token-bucket Lua `eval` (needs lupa, unavailable) is stubbed to always-allow
    since rate-limit internals are not what the auth tests verify."""

    async def eval(self, script, numkeys, *args):  # noqa: A003
        return [1, 999, 0]


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_redis] = override_get_redis


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def db():
    async with _TEST_SESSION_FACTORY() as session:
        yield session


@pytest.fixture
async def fake_redis():
    """Fresh in-memory redis per test (auth token store / unit tests)."""
    r = _StubEvalRedis(decode_responses=True)
    await r.flushall()
    return r


@pytest.fixture
async def auth_client(fake_redis):
    """`client` whose get_redis returns a shared in-memory redis, so tokens
    written during one request are consumable in the next (register→verify)."""
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as async_client:
            yield async_client
    finally:
        app.dependency_overrides[get_redis] = override_get_redis


@pytest.fixture
async def admin_auth_cookies(db):
    admin = User(nickname="admin", is_admin=True)
    db.add(admin)
    await db.flush()
    web_session = WebSession(
        user_id=admin.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(web_session)
    await db.commit()
    return {settings.auth_cookie_name: web_session.id}


@pytest.fixture
def test_session_factory():
    return _TEST_SESSION_FACTORY


@pytest.fixture
def test_engine():
    return _TEST_ENGINE


# Aliases used in v2 plan tests (kept alongside historic names for clarity).
@pytest.fixture
def async_engine():
    return _TEST_ENGINE


@pytest.fixture
async def admin_client(client, admin_auth_cookies):
    """`client` with admin auth cookies pre-attached for v2 admin-API tests."""
    for name, value in admin_auth_cookies.items():
        client.cookies.set(name, value)
    yield client


@pytest.fixture
def generation_task_service(test_session_factory):
    """Minimal v2-test GenerationTaskService — no-op factories; replace per test as needed."""
    from services.generation_task_service import GenerationTaskService

    return GenerationTaskService(
        session_factory=test_session_factory,
        world_creator_factory=lambda: None,
        normalize_world_payload=lambda payload: payload,
        normalize_script_payload=lambda payload: payload,
    )
