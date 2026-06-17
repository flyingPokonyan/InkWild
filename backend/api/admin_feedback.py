"""Admin 用户反馈：列表（可按状态过滤）/ 状态流转 + 备注。写操作经审计。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.user import User
from schemas.feedback import FeedbackAdminOut, FeedbackUpdateIn
from services import feedback_service as fb
from services.audit_service import record_admin_action

router = APIRouter(prefix="/api/admin", tags=["admin-feedback"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _ok(data) -> dict:
    return {"code": 0, "data": data, "message": "ok"}


@router.get("/feedback")
async def list_feedback(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = await fb.list_for_admin(db, status=status, limit=limit, offset=offset)
    return _ok([FeedbackAdminOut.model_validate(r).model_dump(mode="json") for r in rows])


@router.patch("/feedback/{feedback_id}")
async def update_feedback(
    feedback_id: str,
    payload: FeedbackUpdateIn,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        record = await fb.update(
            db,
            feedback_id=feedback_id,
            status=payload.status,
            admin_note=payload.admin_note,
            reply=payload.reply,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await record_admin_action(
        db,
        admin_user=admin,
        action="feedback.update",
        resource_type="feedback",
        resource_id=str(record.id),
        payload=payload.model_dump(exclude_none=True, mode="json"),
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    await db.commit()
    return _ok(FeedbackAdminOut.model_validate(record).model_dump(mode="json"))
