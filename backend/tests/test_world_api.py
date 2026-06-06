from datetime import datetime, timedelta, timezone

import pytest

from config import settings
from models.script import Script
from models.user import User, WebSession
from models.world import World, WorldCharacter


async def _mint_session_cookie(db, user) -> dict:
    ws = WebSession(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(ws)
    await db.commit()
    return {settings.auth_cookie_name: ws.id}


@pytest.mark.asyncio
async def test_list_worlds_empty(client):
    response = await client.get("/api/worlds", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"] == []


@pytest.mark.asyncio
async def test_list_worlds_with_data(client, db):
    world = World(
        name="测试世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        cover_image="https://example.com/legacy-cover.png",
        base_setting="test",
        status="published",
    )
    db.add(world)
    await db.commit()

    response = await client.get("/api/worlds", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["name"] == "测试世界"
    assert data["data"][0]["cover_image"] == "https://example.com/legacy-cover.png"
    assert data["data"][0]["hero_image"] == "https://example.com/legacy-cover.png"


@pytest.mark.asyncio
async def test_list_worlds_has_script_false_without_legacy_or_published_script(client, db):
    world = World(
        name="无脚本世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="test",
        script_setting="",
        status="published",
    )
    db.add(world)
    await db.commit()

    response = await client.get("/api/worlds", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["data"][0]["has_script"] is False


@pytest.mark.asyncio
async def test_list_worlds_has_script_true_with_published_script(client, db):
    world = World(
        name="脚本世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="test",
        script_setting=None,
        status="published",
    )
    db.add(world)
    await db.flush()
    db.add(
        Script(
            world_id=world.id,
            name="已发布剧本",
            description="脚本描述",
            difficulty=2,
            estimated_time="45分钟",
            events_data=[],
            clues_data={},
            endings_data=[],
            script_setting="线索",
            is_published=True,
        )
    )
    await db.commit()

    response = await client.get("/api/worlds", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["data"][0]["has_script"] is True


@pytest.mark.asyncio
async def test_list_worlds_has_script_true_with_legacy_setting(client, db):
    world = World(
        name="旧脚本世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="test",
        script_setting="legacy script text",
        status="published",
    )
    db.add(world)
    await db.commit()

    response = await client.get("/api/worlds", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["data"][0]["has_script"] is True


@pytest.mark.asyncio
async def test_list_worlds_has_script_false_with_unpublished_script_only(client, db):
    world = World(
        name="未发布脚本世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="test",
        script_setting=None,
        status="published",
    )
    db.add(world)
    await db.flush()
    db.add(
        Script(
            world_id=world.id,
            name="未发布剧本",
            description="脚本描述",
            difficulty=2,
            estimated_time="45分钟",
            events_data=[],
            clues_data={},
            endings_data=[],
            script_setting="线索",
            is_published=False,
        )
    )
    await db.commit()

    response = await client.get("/api/worlds", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["data"][0]["has_script"] is False


@pytest.mark.asyncio
async def test_get_world_includes_published_scripts_and_has_script_mode(client, db):
    world = World(
        name="详情世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        cover_image="https://example.com/legacy-cover.png",
        hero_image="https://example.com/hero.png",
        base_setting="test",
        free_setting="夜里总有人失踪\n警署内部有人压案",
        script_setting=None,
        status="published",
    )
    db.add(world)
    await db.flush()
    db.add(
        WorldCharacter(
            world_id=world.id,
            name="记者",
            personality="善于打探消息",
            playable=True,
            description="善于打探消息",
            abilities=["采访"],
            initial_location="白教堂",
            starting_inventory=["旧笔记本"],
        )
    )
    db.add(
        Script(
            world_id=world.id,
            name="已发布剧本",
            description="脚本描述",
            difficulty=2,
            estimated_time="45分钟",
            events_data=[],
            clues_data={},
            endings_data=[],
            script_setting="线索",
            is_published=True,
        )
    )
    db.add(
        Script(
            world_id=world.id,
            name="未发布剧本",
            description="脚本描述",
            difficulty=4,
            estimated_time="60分钟",
            events_data=[],
            clues_data={},
            endings_data=[],
            script_setting="线索",
            is_published=False,
        )
    )
    await db.commit()

    response = await client.get(f"/api/worlds/{world.id}", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["has_script_mode"] is True
    assert data["free_setting"] == "夜里总有人失踪\n警署内部有人压案"
    assert data["cover_image"] == "https://example.com/legacy-cover.png"
    assert data["hero_image"] == "https://example.com/hero.png"
    assert len(data["scripts"]) == 1
    assert data["scripts"][0]["name"] == "已发布剧本"
    assert len(data["characters"]) == 1
    assert data["characters"][0]["name"] == "记者"
    assert data["characters"][0]["starting_location"] == "白教堂"
    assert data["characters"][0]["starting_inventory"] == ["旧笔记本"]


@pytest.mark.asyncio
async def test_get_world_returns_40001_for_unpublished_world(client, db):
    world = World(
        name="未发布世界",
        description="测试",
        genre="悬疑",
        era="现代",
        difficulty=1,
        estimated_time="30分钟",
        base_setting="test",
        status="draft",
    )
    db.add(world)
    await db.commit()

    response = await client.get(f"/api/worlds/{world.id}", headers={"X-Player-Id": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 40001
    assert data["data"] is None


# ---------------------------------------------------------------------------
# Private world owner access (privacy gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_world_owner_can_view_private_world(client, db):
    owner = User(nickname="owner", is_admin=False)
    db.add(owner)
    await db.flush()
    world = World(
        name="私有世界", description="d", genre="g", era="e", difficulty=1,
        estimated_time="30", base_setting="t", status="private",
        created_by_user_id=owner.id,
    )
    db.add(world)
    cookies = await _mint_session_cookie(db, owner)

    response = await client.get(f"/api/worlds/{world.id}", cookies=cookies)

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["name"] == "私有世界"


@pytest.mark.asyncio
async def test_get_world_non_owner_blocked_from_private_world(client, db):
    owner = User(nickname="owner2", is_admin=False)
    intruder = User(nickname="intruder", is_admin=False)
    db.add_all([owner, intruder])
    await db.flush()
    world = World(
        name="别人的私有世界", description="d", genre="g", era="e", difficulty=1,
        estimated_time="30", base_setting="t", status="private",
        created_by_user_id=owner.id,
    )
    db.add(world)
    intruder_cookies = await _mint_session_cookie(db, intruder)

    response = await client.get(f"/api/worlds/{world.id}", cookies=intruder_cookies)

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 40001
    assert data["data"] is None


@pytest.mark.asyncio
async def test_get_world_owner_sees_own_private_script(client, db):
    owner = User(nickname="owner3", is_admin=False)
    db.add(owner)
    await db.flush()
    world = World(
        name="私有带剧本世界", description="d", genre="g", era="e", difficulty=1,
        estimated_time="30", base_setting="t", status="private",
        created_by_user_id=owner.id,
    )
    db.add(world)
    await db.flush()
    db.add(
        Script(
            world_id=world.id, name="我的私有剧本", description="d", difficulty=2,
            estimated_time="45", events_data=[], clues_data={}, endings_data=[],
            script_setting="线索", is_published=False, status="private",
            created_by_user_id=owner.id,
        )
    )
    cookies = await _mint_session_cookie(db, owner)

    response = await client.get(f"/api/worlds/{world.id}", cookies=cookies)

    assert response.status_code == 200
    data = response.json()["data"]
    assert any(s["name"] == "我的私有剧本" for s in data["scripts"])
