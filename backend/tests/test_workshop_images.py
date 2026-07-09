"""Workshop image upload + single-image regeneration tests.

Highest-leverage invariants:
1. Upload validates mime / size and gates on can_create.
2. Regenerate enforces draft ownership and returns the new URL.
3. The regen service refuses to run without an image generator.
"""
import base64
from datetime import datetime, timedelta, timezone

import pytest

from config import settings
from models.draft import ScriptDraft, WorldDraft
from models.user import User, WebSession

# 1×1 transparent PNG (same asset MockImageGenerator uses).
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
_TINY_PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode()


async def _make_user(db, *, can_create: bool, is_admin: bool = False, nickname: str = "u") -> User:
    user = User(nickname=nickname, is_admin=is_admin, can_create=can_create)
    db.add(user)
    await db.flush()
    return user


async def _login(db, client, user: User) -> None:
    session = WebSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(session)
    await db.commit()
    client.cookies.set(settings.auth_cookie_name, session.id)


class _FakeStorage:
    async def save(self, data: bytes, key: str) -> str:
        return f"https://oss.test/{key}"


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_rejects_non_creator(client, db):
    user = await _make_user(db, can_create=False, nickname="reader")
    await _login(db, client, user)
    resp = await client.post(
        "/api/workshop/uploads", json={"image": _TINY_PNG_DATA_URL, "kind": "cover"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_upload_rejects_invalid_data_url(client, db):
    user = await _make_user(db, can_create=True, nickname="creator")
    await _login(db, client, user)
    resp = await client.post(
        "/api/workshop/uploads", json={"image": "not-a-data-url", "kind": "cover"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_oversized(client, db):
    user = await _make_user(db, can_create=True, nickname="creator")
    await _login(db, client, user)
    big = base64.b64encode(b"\x00" * (2 * 1024 * 1024 + 16)).decode()
    resp = await client.post(
        "/api/workshop/uploads",
        json={"image": "data:image/png;base64," + big, "kind": "avatar"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_happy_path(client, db, monkeypatch):
    import api.workshop as workshop

    monkeypatch.setattr(workshop, "get_image_storage", lambda: _FakeStorage())
    user = await _make_user(db, can_create=True, nickname="creator")
    await _login(db, client, user)
    resp = await client.post(
        "/api/workshop/uploads", json={"image": _TINY_PNG_DATA_URL, "kind": "cover"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["url"].startswith("https://oss.test/")


# ---------------------------------------------------------------------------
# Regenerate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_world_image_rejects_non_owner(client, db):
    owner = await _make_user(db, can_create=True, nickname="owner")
    other = await _make_user(db, can_create=True, nickname="intruder")
    draft = WorldDraft(payload={"name": "w"}, created_by_user_id=str(owner.id))
    db.add(draft)
    await db.commit()

    await _login(db, client, other)
    resp = await client.post(
        f"/api/workshop/world-drafts/{draft.id}/regenerate-image",
        json={"target": "cover"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regenerate_world_image_happy_path(client, db, monkeypatch):
    import api.workshop as workshop

    async def _fake_regen(db_, draft_, *, target, hint, prompt, llm_router, image_gen):
        assert target == "cover"
        return "https://oss.test/worlds/cover/new.png"

    async def _fake_router(db_, slot):
        return object()

    async def _fake_image_gen(db_, slot):
        return object()

    monkeypatch.setattr(workshop, "regenerate_world_draft_image", _fake_regen)
    monkeypatch.setattr(workshop, "resolve_slot_router", _fake_router)
    monkeypatch.setattr(workshop, "resolve_slot_image_generator", _fake_image_gen)

    owner = await _make_user(db, can_create=True, nickname="owner")
    draft = WorldDraft(payload={"name": "w"}, created_by_user_id=str(owner.id))
    db.add(draft)
    await db.commit()

    await _login(db, client, owner)
    resp = await client.post(
        f"/api/workshop/world-drafts/{draft.id}/regenerate-image",
        json={"target": "cover", "hint": "更冷一点"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["url"].endswith("new.png")
    await db.refresh(draft)
    assert draft.payload["cover_image"].endswith("new.png")


@pytest.mark.asyncio
async def test_regenerate_world_avatar_persists_character_and_image_map(client, db, monkeypatch):
    import api.workshop as workshop

    async def _fake_regen(db_, draft_, *, target, hint, prompt, llm_router, image_gen):
        assert target == "avatar:琼恩·雪诺"
        return "https://oss.test/characters/jon.png"

    async def _fake_router(db_, slot):
        return object()

    async def _fake_image_gen(db_, slot):
        return object()

    monkeypatch.setattr(workshop, "regenerate_world_draft_image", _fake_regen)
    monkeypatch.setattr(workshop, "resolve_slot_router", _fake_router)
    monkeypatch.setattr(workshop, "resolve_slot_image_generator", _fake_image_gen)

    owner = await _make_user(db, can_create=True, nickname="owner")
    draft = WorldDraft(
        payload={
            "name": "权力的游戏",
            "world_characters": [
                {"name": "琼恩·雪诺", "personality": "x", "avatar": "/static/placeholder-cover.png"}
            ],
            "character_images": {"琼恩·雪诺": "/static/placeholder-cover.png"},
        },
        created_by_user_id=str(owner.id),
    )
    db.add(draft)
    await db.commit()

    await _login(db, client, owner)
    resp = await client.post(
        f"/api/workshop/world-drafts/{draft.id}/regenerate-image",
        json={"target": "avatar:琼恩·雪诺"},
    )
    assert resp.status_code == 200
    await db.refresh(draft)
    assert draft.payload["character_images"]["琼恩·雪诺"].endswith("jon.png")
    assert draft.payload["world_characters"][0]["avatar"].endswith("jon.png")


@pytest.mark.asyncio
async def test_regenerate_script_cover_persists_payload(client, db, monkeypatch):
    import api.workshop as workshop

    async def _fake_regen(db_, draft_, *, hint, prompt, llm_router, image_gen):
        return "https://oss.test/scripts/cover/new.png"

    async def _fake_router(db_, slot):
        return object()

    async def _fake_image_gen(db_, slot):
        return object()

    monkeypatch.setattr(workshop, "regenerate_script_draft_image", _fake_regen)
    monkeypatch.setattr(workshop, "resolve_slot_router", _fake_router)
    monkeypatch.setattr(workshop, "resolve_slot_image_generator", _fake_image_gen)

    owner = await _make_user(db, can_create=True, nickname="owner")
    # ScriptDraft requires a real world_id FK; use the app's World model.
    from models.world import World

    published_world = World(
        name="w",
        description="d",
        genre="g",
        era="e",
        difficulty=3,
        estimated_time="30m",
        cover_image="",
        base_setting="b",
        locations_data=[],
        status="private",
        play_count=0,
        created_by_user_id=str(owner.id),
    )
    db.add(published_world)
    await db.flush()
    draft = ScriptDraft(
        world_id=published_world.id,
        payload={"name": "s", "cover_image": "/static/placeholder-cover.png"},
        created_by_user_id=str(owner.id),
    )
    db.add(draft)
    await db.commit()

    await _login(db, client, owner)
    resp = await client.post(
        f"/api/workshop/script-drafts/{draft.id}/regenerate-image",
        json={"target": "cover"},
    )
    assert resp.status_code == 200
    await db.refresh(draft)
    assert draft.payload["cover_image"].endswith("new.png")


@pytest.mark.asyncio
async def test_regenerate_service_requires_image_gen():
    from services.image_regeneration import (
        ImageRegenerationError,
        regenerate_world_draft_image,
    )

    draft = WorldDraft(payload={"name": "w"}, created_by_user_id="x")
    with pytest.raises(ImageRegenerationError):
        await regenerate_world_draft_image(
            None, draft, target="hero", hint="", llm_router=None, image_gen=None
        )
