"""Admin 内容事后治理：跨用户列已发布世界/剧本 + 强制下架。

与 admin_review.py（准入：审草稿→发布）互补。强制下架复用
publish_service.withdraw_*(by_admin=True)：跳过 ownership，→ WITHDRAWN 终态。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from engine.content_status import ContentStatus
from models.script import Script
from models.user import User
from models.world import World
from services import publish_service
from services.audit_service import record_admin_action

router = APIRouter(
    prefix="/api/admin/content",
    tags=["admin-content"],
    dependencies=[Depends(get_current_admin_user)],
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def _author_names(db: AsyncSession, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(select(User).where(User.id.in_(user_ids)))
    ).scalars().all()
    return {str(u.id): (u.nickname or "") for u in rows}


def _item(obj) -> dict:
    return {
        "id": str(obj.id),
        "name": obj.name,
        "author_id": str(obj.created_by_user_id) if obj.created_by_user_id else None,
        "status": obj.status,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
    }


_LISTABLE_STATUSES = {ContentStatus.PUBLISHED.value, ContentStatus.WITHDRAWN.value}


def _resolve_status(status: str) -> str:
    if status not in _LISTABLE_STATUSES:
        raise HTTPException(status_code=422, detail=f"unsupported status: {status}")
    return status


@router.get("/worlds")
async def list_content_worlds(
    q: str | None = Query(None),
    status: str = Query(ContentStatus.PUBLISHED.value),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """跨用户列内容供事后治理。status=published 强制下架；status=withdrawn 恢复。"""
    stmt = (
        select(World)
        .where(World.status == _resolve_status(status))
        .order_by(World.created_at.desc())
    )
    if q:
        stmt = stmt.where(World.name.ilike(f"%{q}%"))
    worlds = (await db.execute(stmt)).scalars().all()
    names = await _author_names(
        db, {str(w.created_by_user_id) for w in worlds if w.created_by_user_id}
    )
    items = [
        {**_item(w), "author": names.get(str(w.created_by_user_id), "")}
        for w in worlds
    ]
    return {"code": 0, "data": {"items": items}, "message": "ok"}


@router.get("/scripts")
async def list_content_scripts(
    q: str | None = Query(None),
    status: str = Query(ContentStatus.PUBLISHED.value),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = (
        select(Script)
        .where(Script.status == _resolve_status(status))
        .order_by(Script.created_at.desc())
    )
    if q:
        stmt = stmt.where(Script.name.ilike(f"%{q}%"))
    scripts = (await db.execute(stmt)).scalars().all()
    names = await _author_names(
        db, {str(s.created_by_user_id) for s in scripts if s.created_by_user_id}
    )
    items = [
        {**_item(s), "author": names.get(str(s.created_by_user_id), "")}
        for s in scripts
    ]
    return {"code": 0, "data": {"items": items}, "message": "ok"}


@router.post("/worlds/{world_id}/withdraw")
async def admin_withdraw_world(
    world_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    try:
        world = await publish_service.withdraw_world(
            db, world_id=world_id, actor_user_id=admin.id, by_admin=True
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await record_admin_action(
        db,
        admin_user=admin,
        action="content.world.withdraw",
        resource_type="world",
        resource_id=world_id,
        payload={"name": world.name},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {
        "code": 0,
        "data": {"id": world_id, "status": world.status},
        "message": "ok",
    }


@router.post("/scripts/{script_id}/withdraw")
async def admin_withdraw_script(
    script_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    try:
        script = await publish_service.withdraw_script(
            db, script_id=script_id, actor_user_id=admin.id, by_admin=True
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await record_admin_action(
        db,
        admin_user=admin,
        action="content.script.withdraw",
        resource_type="script",
        resource_id=script_id,
        payload={"name": script.name},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {
        "code": 0,
        "data": {"id": script_id, "status": script.status},
        "message": "ok",
    }


@router.post("/worlds/{world_id}/restore")
async def admin_restore_world(
    world_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    try:
        world = await publish_service.restore_world(
            db, world_id=world_id, actor_user_id=admin.id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await record_admin_action(
        db,
        admin_user=admin,
        action="content.world.restore",
        resource_type="world",
        resource_id=world_id,
        payload={"name": world.name},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {
        "code": 0,
        "data": {"id": world_id, "status": world.status},
        "message": "ok",
    }


@router.post("/scripts/{script_id}/restore")
async def admin_restore_script(
    script_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
) -> dict:
    try:
        script = await publish_service.restore_script(
            db, script_id=script_id, actor_user_id=admin.id
        )
    except ValueError as e:
        # 所属世界仍下架 → 业务可恢复错误，给 409 而非 404。
        detail = str(e)
        status_code = 409 if "请先恢复所属世界" in detail else 404
        raise HTTPException(status_code=status_code, detail=detail)
    await record_admin_action(
        db,
        admin_user=admin,
        action="content.script.restore",
        resource_type="script",
        resource_id=script_id,
        payload={"name": script.name},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return {
        "code": 0,
        "data": {"id": script_id, "status": script.status},
        "message": "ok",
    }
