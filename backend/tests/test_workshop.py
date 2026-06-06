"""Workshop API permission tests.

Covers the two highest-leverage invariants of the admin→user creator split:

1. _require_can_create gate: a logged-in user without can_create cannot kick off
   a generation task (returns 403 with code 40300).
2. Ownership filter on draft list: user A does not see user B's drafts in
   GET /api/workshop/world-drafts; admin sees both.
"""
from datetime import datetime, timedelta, timezone

import pytest

from config import settings
from models.draft import WorldDraft
from models.user import User, WebSession


async def _make_user(db, *, can_create: bool, is_admin: bool = False, nickname: str = "u") -> User:
    user = User(nickname=nickname, is_admin=is_admin, can_create=can_create)
    db.add(user)
    await db.flush()
    return user


async def _make_session(db, user: User) -> str:
    session = WebSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(session)
    await db.commit()
    return session.id


@pytest.mark.asyncio
async def test_non_creator_blocked_from_world_generation(client, db):
    """A logged-in user without can_create gets 403 (40300) on world-generation."""
    user = await _make_user(db, can_create=False, nickname="reader")
    session_id = await _make_session(db, user)
    client.cookies.set(settings.auth_cookie_name, session_id)

    resp = await client.post(
        "/api/workshop/world-generation-tasks",
        json={"description": "test", "genre": "", "era": ""},
    )
    assert resp.status_code == 403
    body = resp.json()
    # FastAPI wraps HTTPException(detail={...}) → {"detail": {...}}
    detail = body.get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == 40300


@pytest.mark.asyncio
async def test_world_drafts_listing_respects_ownership(client, db):
    """User A's GET /world-drafts only returns their own; admin sees all."""
    user_a = await _make_user(db, can_create=True, nickname="alice")
    user_b = await _make_user(db, can_create=True, nickname="bob")
    admin = await _make_user(db, can_create=True, is_admin=True, nickname="root")

    db.add(WorldDraft(payload={"name": "alice-draft"}, created_by_user_id=str(user_a.id)))
    db.add(WorldDraft(payload={"name": "bob-draft"}, created_by_user_id=str(user_b.id)))
    await db.commit()

    # user A — sees only their own
    sid_a = await _make_session(db, user_a)
    client.cookies.set(settings.auth_cookie_name, sid_a)
    resp = await client.get("/api/workshop/world-drafts")
    assert resp.status_code == 200
    names = [d["payload"].get("name") for d in resp.json()["data"]]
    assert names == ["alice-draft"]

    # admin — sees both
    sid_admin = await _make_session(db, admin)
    client.cookies.set(settings.auth_cookie_name, sid_admin)
    resp = await client.get("/api/workshop/world-drafts")
    assert resp.status_code == 200
    names = sorted(d["payload"].get("name") for d in resp.json()["data"])
    assert names == ["alice-draft", "bob-draft"]
