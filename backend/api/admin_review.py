"""Admin content review queue.

Lists drafts whose review_status == 'submitted' (worlds + scripts) and lets an
admin approve (→ publish) or reject (→ rejected + reason). All writes are
audited via ``record_admin_action``.

Review state lives on the draft, so approving a revision of a published work
swaps the live content in place without ever taking it offline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_admin_user, get_db
from models.draft import ScriptDraft, WorldDraft
from models.user import User
from services import notification_service as ns
from services import publish_service
from services.audit_service import record_admin_action

router = APIRouter(prefix="/api/admin", tags=["admin-review"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


class RejectRequest(BaseModel):
    note: str | None = None


async def _submitter_names(db: AsyncSession, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    return {str(u.id): (u.nickname or "") for u in rows}


@router.get("/reviews")
async def list_reviews(
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """All submitted world + script drafts awaiting review."""
    world_drafts = (
        await db.execute(
            select(WorldDraft)
            .where(WorldDraft.review_status == "submitted")
            .order_by(WorldDraft.updated_at.asc())
        )
    ).scalars().all()
    script_drafts = (
        await db.execute(
            select(ScriptDraft)
            .where(ScriptDraft.review_status == "submitted")
            .order_by(ScriptDraft.updated_at.asc())
        )
    ).scalars().all()

    names = await _submitter_names(
        db,
        {str(d.created_by_user_id) for d in world_drafts}
        | {str(d.created_by_user_id) for d in script_drafts},
    )

    def _item(d, kind: str) -> dict:
        payload = d.payload or {}
        return {
            "kind": kind,
            "draft_id": str(d.id),
            "name": payload.get("name") or ("未命名世界" if kind == "world" else "未命名剧本"),
            "description": payload.get("description", ""),
            "world_id": str(d.world_id) if d.world_id else None,
            "submitter": names.get(str(d.created_by_user_id), ""),
            "submitter_id": str(d.created_by_user_id),
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }

    items = [_item(d, "world") for d in world_drafts] + [
        _item(d, "script") for d in script_drafts
    ]
    return {"code": 0, "data": {"reviews": items}, "message": "ok"}


@router.get("/reviews/{kind}/{draft_id}")
async def get_review(
    kind: str,
    draft_id: str,
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if kind == "world":
        draft = await db.get(WorldDraft, draft_id)
    elif kind == "script":
        draft = await db.get(ScriptDraft, draft_id)
    else:
        raise HTTPException(status_code=400, detail="kind 必须是 world 或 script")
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return {
        "code": 0,
        "data": {
            "kind": kind,
            "draft_id": str(draft.id),
            "review_status": draft.review_status,
            "review_note": draft.review_note,
            "world_id": str(draft.world_id) if draft.world_id else None,
            "payload": draft.payload,
        },
        "message": "ok",
    }


@router.post("/reviews/{kind}/{draft_id}/approve")
async def approve_review(
    kind: str,
    draft_id: str,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        if kind == "world":
            obj = await publish_service.approve_world_draft(db, draft_id=draft_id)
            resource_type = "world"
        elif kind == "script":
            obj = await publish_service.approve_script_draft(db, draft_id=draft_id)
            resource_type = "script"
        else:
            raise HTTPException(status_code=400, detail="kind 必须是 world 或 script")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await record_admin_action(
        db,
        admin_user=admin,
        action=f"{resource_type}.review_approve",
        resource_type=resource_type,
        resource_id=str(obj.id),
        payload={"draft_id": draft_id},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    # 通知作者：内容已通过审核并发布
    DraftModel = WorldDraft if kind == "world" else ScriptDraft
    draft_row = (
        await db.execute(select(DraftModel).where(DraftModel.id == draft_id))
    ).scalar_one_or_none()
    if draft_row is not None:
        title_text = getattr(obj, "name", None) or "你的作品"
        link = f"/worlds/{obj.id}" if kind == "world" else f"/worlds/{getattr(obj, 'world_id', '')}"
        await ns.notify(
            db,
            user_id=draft_row.created_by_user_id,
            type="review_approved",
            title=f"《{title_text}》已通过审核",
            body="你的内容已发布，现在所有人都能体验了。",
            link=link,
            payload={"kind": kind, "draft_id": draft_id, "target_id": str(obj.id)},
        )
    await db.commit()
    return {"code": 0, "data": {"id": str(obj.id), "status": obj.status}, "message": "ok"}


@router.post("/reviews/{kind}/{draft_id}/reject")
async def reject_review(
    kind: str,
    draft_id: str,
    payload: RejectRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        if kind == "world":
            draft = await publish_service.reject_world_draft(db, draft_id=draft_id, note=payload.note)
        elif kind == "script":
            draft = await publish_service.reject_script_draft(db, draft_id=draft_id, note=payload.note)
        else:
            raise HTTPException(status_code=400, detail="kind 必须是 world 或 script")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await record_admin_action(
        db,
        admin_user=admin,
        action=f"{kind}.review_reject",
        resource_type=kind,
        resource_id=str(draft.id),
        payload={"draft_id": draft_id, "note": payload.note},
        ip_address=_client_ip(request),
        user_agent=_ua(request),
    )
    # 通知作者：内容未通过审核（带驳回理由）
    await ns.notify(
        db,
        user_id=draft.created_by_user_id,
        type="review_rejected",
        title="作品未通过审核",
        body=(payload.note or "请根据审核意见修改后重新提交。"),
        link="/workshop",
        payload={"kind": kind, "draft_id": draft_id, "note": payload.note},
    )
    await db.commit()
    return {"code": 0, "data": {"review_status": draft.review_status}, "message": "ok"}
