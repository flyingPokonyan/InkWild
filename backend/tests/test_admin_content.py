import pytest
from httpx import AsyncClient

from models.user import User
from models.world import World


def _published_world(owner_id: str, name: str = "违规世界") -> World:
    return World(
        name=name,
        description="测试用世界",
        genre="悬疑",
        era="现代",
        difficulty=2,
        estimated_time="30分钟",
        base_setting="测试设定",
        status="published",
        created_by_user_id=owner_id,
    )


@pytest.mark.asyncio
async def test_admin_withdraw_world_terminal(admin_client: AsyncClient, db):
    owner = User(nickname="creator", is_admin=False)
    db.add(owner)
    await db.flush()
    world = _published_world(owner.id)
    db.add(world)
    await db.commit()

    # 已发布列表能看到
    r = await admin_client.get("/api/admin/content/worlds")
    assert r.status_code == 200
    assert str(world.id) in [w["id"] for w in r.json()["data"]["items"]]

    # admin 强制下架 → 终态 withdrawn
    r = await admin_client.post(f"/api/admin/content/worlds/{world.id}/withdraw")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "withdrawn"

    # 从已发布列表消失
    r = await admin_client.get("/api/admin/content/worlds")
    assert str(world.id) not in [w["id"] for w in r.json()["data"]["items"]]


@pytest.mark.asyncio
async def test_admin_withdraw_then_restore_world(admin_client: AsyncClient, db):
    owner = User(nickname="creator2", is_admin=False)
    db.add(owner)
    await db.flush()
    world = _published_world(owner.id, name="可恢复世界")
    db.add(world)
    await db.commit()

    # 下架
    r = await admin_client.post(f"/api/admin/content/worlds/{world.id}/withdraw")
    assert r.status_code == 200

    # 出现在「已下架」列表
    r = await admin_client.get("/api/admin/content/worlds?status=withdrawn")
    assert r.status_code == 200
    assert str(world.id) in [w["id"] for w in r.json()["data"]["items"]]

    # 恢复 → 重新 published
    r = await admin_client.post(f"/api/admin/content/worlds/{world.id}/restore")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "published"

    # 回到已发布列表，且从已下架列表消失
    r = await admin_client.get("/api/admin/content/worlds")
    assert str(world.id) in [w["id"] for w in r.json()["data"]["items"]]
    r = await admin_client.get("/api/admin/content/worlds?status=withdrawn")
    assert str(world.id) not in [w["id"] for w in r.json()["data"]["items"]]


@pytest.mark.asyncio
async def test_content_list_rejects_unsupported_status(admin_client: AsyncClient):
    r = await admin_client.get("/api/admin/content/worlds?status=private")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_withdraw_missing_world_404(admin_client: AsyncClient):
    r = await admin_client.post(
        "/api/admin/content/worlds/00000000-0000-0000-0000-000000000000/withdraw"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_blocked(client: AsyncClient):
    r = await client.get("/api/admin/content/worlds")
    assert r.status_code in (401, 403)
