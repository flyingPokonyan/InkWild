"""Smoke tests for the admin content review queue API."""
import pytest

from models.draft import WorldDraft
from models.user import User
from services.publish_service import save_world_as_private, submit_world_for_review


def _world_payload():
    return {
        "name": "审核世界",
        "description": "desc",
        "genre": "mystery",
        "era": "modern",
        "difficulty": 3,
        "estimated_time": "30",
        "base_setting": "base",
        "locations": [],
        "world_characters": [],
    }


async def _make_submitted_world_draft(db) -> tuple[WorldDraft, User]:
    creator = User(nickname="creator", is_admin=False)
    db.add(creator)
    await db.flush()
    draft = WorldDraft(payload=_world_payload(), created_by_user_id=creator.id)
    db.add(draft)
    await db.commit()
    await save_world_as_private(db, draft_id=draft.id, actor_user_id=creator.id)
    await submit_world_for_review(db, draft_id=draft.id, actor_user_id=creator.id)
    return draft, creator


@pytest.mark.asyncio
async def test_list_reviews_shows_submitted_world(admin_client, db):
    draft, _ = await _make_submitted_world_draft(db)

    resp = await admin_client.get("/api/admin/reviews")
    assert resp.status_code == 200
    data = resp.json()["data"]["reviews"]
    assert any(r["draft_id"] == str(draft.id) and r["kind"] == "world" for r in data)


@pytest.mark.asyncio
async def test_approve_world_review_publishes(admin_client, db):
    from models.world import World

    draft, _ = await _make_submitted_world_draft(db)

    resp = await admin_client.post(f"/api/admin/reviews/world/{draft.id}/approve")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "published"

    await db.refresh(draft)
    world = await db.get(World, draft.world_id)
    assert world.status == "published"


@pytest.mark.asyncio
async def test_reject_world_review_records_reason(admin_client, db):
    draft, _ = await _make_submitted_world_draft(db)

    resp = await admin_client.post(
        f"/api/admin/reviews/world/{draft.id}/reject", json={"note": "需要更多线索"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["review_status"] == "rejected"

    await db.refresh(draft)
    assert draft.review_note == "需要更多线索"


@pytest.mark.asyncio
async def test_reviews_require_admin(client, db):
    """Non-admin (anonymous) is rejected by the admin auth dependency."""
    resp = await client.get("/api/admin/reviews")
    assert resp.status_code in (401, 403)
