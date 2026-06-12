from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from models.game import TokenUsage
from models.user import AuthIdentity, User
from utils import utcnow


async def _add_password_user(db, email: str, *, verified: bool) -> User:
    user = User(nickname=email.split("@", 1)[0])
    db.add(user)
    await db.flush()
    db.add(
        AuthIdentity(
            user_id=user.id,
            provider="password",
            provider_user_id=email,
            email=email,
            verified_at=utcnow() if verified else None,
        )
    )
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_admin_users_marks_and_filters_verified_users(client, admin_auth_cookies, db):
    verified = await _add_password_user(db, "verified@example.com", verified=True)
    unverified = await _add_password_user(db, "unverified@example.com", verified=False)

    response = await client.get("/api/admin/users", cookies=admin_auth_cookies)
    assert response.status_code == 200
    data = response.json()["data"]
    by_id = {item["id"]: item for item in data["items"]}

    assert by_id[verified.id]["is_verified"] is True
    assert by_id[verified.id]["verified_at"].endswith("Z")
    assert by_id[unverified.id]["is_verified"] is False
    assert by_id[unverified.id]["verified_at"] is None
    assert data["summary"]["verified_count"] >= 1
    assert data["summary"]["unverified_count"] >= 1

    verified_response = await client.get(
        "/api/admin/users?verified=verified",
        cookies=admin_auth_cookies,
    )
    assert verified_response.status_code == 200
    verified_items = verified_response.json()["data"]["items"]
    assert [item["id"] for item in verified_items] == [verified.id]


@pytest.mark.asyncio
async def test_admin_dashboard_counts_verified_signups_only(client, admin_auth_cookies, db):
    recent = await _add_password_user(db, "recent@example.com", verified=True)
    stale = await _add_password_user(db, "stale@example.com", verified=True)
    pending = await _add_password_user(db, "pending@example.com", verified=False)

    stale_identity = (
        await db.execute(select(AuthIdentity).where(AuthIdentity.user_id == stale.id))
    ).scalar_one()
    stale_identity.verified_at = utcnow() - timedelta(days=8)
    await db.commit()

    response = await client.get("/api/admin/dashboard/kpis", cookies=admin_auth_cookies)
    assert response.status_code == 200
    data = response.json()["data"]

    assert recent.id
    assert pending.id
    assert data["new_users_7d"] == 1


@pytest.mark.asyncio
async def test_admin_cost_kpis_use_beijing_day_boundary(client, admin_auth_cookies, db, monkeypatch):
    from services import analytics_service

    fake_now = utcnow().replace(hour=2, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(analytics_service, "utcnow", lambda: fake_now)
    db.add_all(
        [
            TokenUsage(
                task_id=str(uuid4()),
                purpose="test",
                provider="test",
                model="test",
                input_tokens=0,
                output_tokens=0,
                cost_cents=123,
                created_at=fake_now - timedelta(minutes=1),
            ),
            TokenUsage(
                task_id=str(uuid4()),
                purpose="test",
                provider="test",
                model="test",
                input_tokens=0,
                output_tokens=0,
                cost_cents=456,
                created_at=fake_now.replace(hour=15) - timedelta(days=1),
            ),
        ]
    )
    await db.commit()

    response = await client.get("/api/admin/dashboard/kpis", cookies=admin_auth_cookies)
    assert response.status_code == 200
    spend = response.json()["data"]["spend"]

    assert spend["today_cents"] == 123
