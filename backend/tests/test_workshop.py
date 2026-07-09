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
from models.world import World


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


@pytest.mark.asyncio
async def test_worlds_listing_prefers_linked_draft_cover(client, db):
    """A saved private world card should show the latest regenerated draft cover."""
    owner = await _make_user(db, can_create=True, nickname="owner")
    world = World(
        name="哈利·波特",
        description="奇幻冒险",
        genre="奇幻冒险",
        era="二十世纪九十年代至二十一世纪初（魔法英国）",
        difficulty=3,
        estimated_time="30m",
        cover_image="/static/placeholder-cover.png",
        hero_image="/static/placeholder-cover.png",
        base_setting="b",
        locations_data=[],
        status="private",
        play_count=0,
        created_by_user_id=str(owner.id),
    )
    db.add(world)
    await db.flush()
    draft = WorldDraft(
        world_id=world.id,
        payload={
            "name": "哈利·波特",
            "cover_image": "https://oss.test/worlds/cover/new.png",
            "hero_image": "/static/placeholder-cover.png",
        },
        created_by_user_id=str(owner.id),
    )
    db.add(draft)
    await db.commit()

    sid = await _make_session(db, owner)
    client.cookies.set(settings.auth_cookie_name, sid)
    resp = await client.get("/api/workshop/worlds")

    assert resp.status_code == 200
    items = resp.json()["data"]["published"]
    item = next(w for w in items if w["id"] == str(world.id))
    assert item["cover_image"] == "https://oss.test/worlds/cover/new.png"
    assert item["hero_image"] == "https://oss.test/worlds/cover/new.png"
    assert item["has_draft"] is True
    assert item["draft_id"] == str(draft.id)


@pytest.mark.asyncio
async def test_worlds_listing_drops_missing_local_cover(client, db):
    """Missing local static files should fall back instead of rendering a blank cover layer."""
    owner = await _make_user(db, can_create=True, nickname="owner")
    world = World(
        name="lost-image",
        description="d",
        genre="g",
        era="e",
        difficulty=3,
        estimated_time="30m",
        cover_image="/static/images/worlds/cover/not-found.png",
        hero_image="/static/placeholder-cover.png",
        base_setting="b",
        locations_data=[],
        status="private",
        play_count=0,
        created_by_user_id=str(owner.id),
    )
    db.add(world)
    await db.commit()

    sid = await _make_session(db, owner)
    client.cookies.set(settings.auth_cookie_name, sid)
    resp = await client.get("/api/workshop/worlds")

    assert resp.status_code == 200
    item = next(w for w in resp.json()["data"]["published"] if w["id"] == str(world.id))
    assert item["cover_image"] == ""
    assert item["hero_image"] == ""


@pytest.mark.asyncio
async def test_world_draft_detail_drops_missing_local_cover(client, db):
    owner = await _make_user(db, can_create=True, nickname="owner")
    draft = WorldDraft(
        payload={
            "name": "lost-image-draft",
            "cover_image": "/static/images/worlds/cover/not-found.png",
            "hero_image": "/static/placeholder-cover.png",
        },
        created_by_user_id=str(owner.id),
    )
    db.add(draft)
    await db.commit()

    sid = await _make_session(db, owner)
    client.cookies.set(settings.auth_cookie_name, sid)
    resp = await client.get(f"/api/workshop/world-drafts/{draft.id}")

    assert resp.status_code == 200
    payload = resp.json()["data"]["payload"]
    assert payload["cover_image"] == ""
    assert payload["hero_image"] == ""
