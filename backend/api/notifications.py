"""用户端通知 API：个人通知 + 系统公告（一个铃铛消费一套接口）。

`GET /api/notifications/summary` 是唯一被前端轮询的廉价端点（两个 count）；
列表在打开弹窗时才拉。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db
from models.user import User
from schemas.notification import (
    AnnouncementListOut,
    AnnouncementOut,
    NotificationListOut,
    NotificationOut,
    NotificationSummaryOut,
)
from services import announcement_service as anns
from services import notification_service as ns

router = APIRouter(prefix="/api", tags=["notifications"])


def _ok(data: dict) -> dict:
    return {"code": 0, "data": data, "message": "ok"}


# ---------- 汇总（轮询） ----------

@router.get("/notifications/summary")
async def get_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    n = await ns.unread_count(db, user_id=user.id)
    m = await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at)
    return _ok(NotificationSummaryOut(notifications=n, announcements=m).model_dump())


# ---------- 个人通知 ----------

@router.get("/notifications")
async def list_notifications(
    limit: int = Query(20, ge=1, le=50),
    before: datetime | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await ns.list_for_user(db, user_id=user.id, limit=limit, before=before)
    next_before = rows[-1].created_at if len(rows) == limit else None
    out = NotificationListOut(
        items=[NotificationOut.model_validate(r) for r in rows],
        next_before=next_before,
    )
    return _ok(out.model_dump(mode="json"))


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ns.mark_read(db, user_id=user.id, notification_id=notification_id)
    await db.commit()
    return _ok({"ok": True})


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    affected = await ns.mark_all_read(db, user_id=user.id)
    await db.commit()
    return _ok({"affected": affected})


# ---------- 系统公告 ----------

@router.get("/announcements")
async def list_announcements(
    limit: int = Query(20, ge=1, le=50),
    before: datetime | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await anns.list_for_user(
        db, user_id=user.id, user_created_at=user.created_at, limit=limit, before=before
    )
    items = [
        AnnouncementOut(
            id=ann.id, title=ann.title, body=ann.body, image_url=ann.image_url,
            level=ann.level, published_at=ann.published_at, read=read,
        )
        for ann, read in rows
    ]
    next_before = rows[-1][0].published_at if len(rows) == limit else None
    out = AnnouncementListOut(items=items, next_before=next_before)
    return _ok(out.model_dump(mode="json"))


@router.post("/announcements/{announcement_id}/read")
async def mark_announcement_read(
    announcement_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await anns.mark_read(db, user_id=user.id, announcement_id=announcement_id)
    await db.commit()
    return _ok({"ok": True})


@router.post("/announcements/read-all")
async def mark_all_announcements_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    affected = await anns.mark_all_read(db, user_id=user.id, user_created_at=user.created_at)
    await db.commit()
    return _ok({"affected": affected})
