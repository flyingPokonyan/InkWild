"""Admin 系统公告管理：列表（含草稿）/ 创建 / 编辑 / 发布 / 下架。

所有写操作经 ``record_admin_action`` 审计。公告发给全体用户，发布后进入用户端
铃铛的「系统公告」tab。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.user import User
from schemas.notification import (
    AnnouncementAdminOut,
    AnnouncementCreateIn,
    AnnouncementUpdateIn,
)
from services import announcement_service as anns
from services.audit_service import record_admin_action

router = APIRouter(prefix="/api/admin", tags=["admin-announcements"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _ok(data) -> dict:
    return {"code": 0, "data": data, "message": "ok"}


@router.get("/announcements")
async def list_announcements(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await anns.list_all(db, limit=limit, offset=offset)
    return _ok([AnnouncementAdminOut.model_validate(r).model_dump(mode="json") for r in rows])


@router.post("/announcements")
async def create_announcement(
    payload: AnnouncementCreateIn,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    a = await anns.create(
        db, created_by=admin.id, title=payload.title, body=payload.body,
        level=payload.level, expires_at=payload.expires_at,
    )
    await record_admin_action(
        db, admin_user=admin, action="announcement.create",
        resource_type="announcement", resource_id=str(a.id),
        payload={"title": a.title, "level": a.level},
        ip_address=_client_ip(request), user_agent=_ua(request),
    )
    await db.commit()
    return _ok(AnnouncementAdminOut.model_validate(a).model_dump(mode="json"))


@router.patch("/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdateIn,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        a = await anns.update(
            db, announcement_id=announcement_id, title=payload.title, body=payload.body,
            level=payload.level, expires_at=payload.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await record_admin_action(
        db, admin_user=admin, action="announcement.update",
        resource_type="announcement", resource_id=str(a.id),
        payload=payload.model_dump(exclude_none=True, mode="json"),
        ip_address=_client_ip(request), user_agent=_ua(request),
    )
    await db.commit()
    return _ok(AnnouncementAdminOut.model_validate(a).model_dump(mode="json"))


@router.post("/announcements/{announcement_id}/publish")
async def publish_announcement(
    announcement_id: str,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        a = await anns.publish(db, announcement_id=announcement_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await record_admin_action(
        db, admin_user=admin, action="announcement.publish",
        resource_type="announcement", resource_id=str(a.id),
        payload=None, ip_address=_client_ip(request), user_agent=_ua(request),
    )
    await db.commit()
    return _ok(AnnouncementAdminOut.model_validate(a).model_dump(mode="json"))


@router.post("/announcements/{announcement_id}/unpublish")
async def unpublish_announcement(
    announcement_id: str,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        a = await anns.unpublish(db, announcement_id=announcement_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await record_admin_action(
        db, admin_user=admin, action="announcement.unpublish",
        resource_type="announcement", resource_id=str(a.id),
        payload=None, ip_address=_client_ip(request), user_agent=_ua(request),
    )
    await db.commit()
    return _ok(AnnouncementAdminOut.model_validate(a).model_dump(mode="json"))
