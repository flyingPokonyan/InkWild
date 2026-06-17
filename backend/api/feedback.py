"""用户反馈提交 API。需登录；可选附截图（base64 data URL）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db
from models.user import User
from schemas.feedback import FeedbackCreateIn, FeedbackEventOut, FeedbackThreadOut
from services import feedback_service as fb
from services.image_storage import decode_data_url_image, get_image_storage, make_image_key

router = APIRouter(prefix="/api", tags=["feedback"])

_FEEDBACK_IMAGE_MAX_BYTES = 4 * 1024 * 1024


def _ok(data) -> dict:
    return {"code": 0, "data": data, "message": "ok"}


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackCreateIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    image_url: str | None = None
    if payload.image:
        data, ext = decode_data_url_image(payload.image, max_bytes=_FEEDBACK_IMAGE_MAX_BYTES)
        storage = get_image_storage()
        key = make_image_key("feedback", user.id, ext)
        image_url = await storage.save(data, key)

    ua = request.headers.get("user-agent")
    record = await fb.create(
        db,
        user_id=user.id,
        category=payload.category,
        content=payload.content,
        image_url=image_url,
        page_url=payload.page_url,
        contact=payload.contact,
        user_agent=ua[:400] if ua else None,
    )
    await db.commit()
    return _ok({"id": record.id})


@router.get("/feedback/{feedback_id}")
async def get_feedback_thread(
    feedback_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    record, events = await fb.get_thread(db, feedback_id=feedback_id, user_id=user.id)
    out = FeedbackThreadOut(
        id=record.id,
        category=record.category,
        content=record.content,
        image_url=record.image_url,
        status=record.status,
        created_at=record.created_at,
        events=[FeedbackEventOut.model_validate(e) for e in events],
    )
    return _ok(out.model_dump(mode="json"))
