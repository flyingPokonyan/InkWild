"""用户反馈 service。

用户提交一行；新反馈给全体 admin 发一条站内通知（FYI ping，详情在 admin 后台处理）。
状态流转 new → triaged → resolved。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.error_handler import AppError
from models.feedback import Feedback, FeedbackEvent
from models.user import User
from services import notification_service as ns

CATEGORIES = {"bug", "suggestion"}
STATUSES = {"new", "triaged", "resolved"}

_CATEGORY_LABEL = {"bug": "问题反馈", "suggestion": "优化建议"}
_STATUS_LABEL = {"new": "待处理", "triaged": "处理中", "resolved": "已解决"}


async def create(
    db: AsyncSession,
    *,
    user_id: str | None,
    category: str,
    content: str,
    image_url: str | None = None,
    page_url: str | None = None,
    contact: str | None = None,
    user_agent: str | None = None,
) -> Feedback:
    if category not in CATEGORIES:
        raise AppError(42240, "未知的反馈类型", status_code=422)
    fb = Feedback(
        user_id=user_id,
        category=category,
        content=content.strip(),
        image_url=image_url,
        page_url=page_url,
        contact=contact,
        user_agent=user_agent,
        status="new",
    )
    db.add(fb)
    await db.flush()
    await _notify_admins(db, fb)
    return fb


async def _notify_admins(db: AsyncSession, fb: Feedback) -> None:
    admin_ids = (
        await db.execute(select(User.id).where(User.is_admin.is_(True)))
    ).scalars().all()
    label = _CATEGORY_LABEL.get(fb.category, "反馈")
    preview = fb.content[:60] + ("…" if len(fb.content) > 60 else "")
    for admin_id in admin_ids:
        await ns.notify(
            db,
            user_id=admin_id,
            type="feedback_new",
            title=f"新的{label}",
            body=preview,
            payload={"feedback_id": fb.id, "category": fb.category},
        )


async def list_for_admin(
    db: AsyncSession, *, status: str | None = None, limit: int = 50, offset: int = 0
) -> list[Feedback]:
    q = select(Feedback)
    if status is not None:
        q = q.where(Feedback.status == status)
    q = q.order_by(Feedback.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(q)).scalars().all())


async def update(
    db: AsyncSession,
    *,
    feedback_id: str,
    status: str | None = None,
    admin_note: str | None = None,
    reply: str | None = None,
) -> Feedback:
    fb = await db.get(Feedback, feedback_id)
    if fb is None:
        raise ValueError("反馈不存在")

    status_changed = False
    if status is not None:
        if status not in STATUSES:
            raise AppError(42241, "未知的反馈状态", status_code=422)
        status_changed = status != fb.status
        fb.status = status
    if admin_note is not None:  # 内部备注，不进通知、不进时间线
        fb.admin_note = admin_note

    reply_text = reply.strip() if reply else ""
    if reply_text:
        fb.reply = reply_text

    # 累积时间线事件（解决记录全貌）
    if status_changed:
        db.add(FeedbackEvent(feedback_id=fb.id, kind="status", status=fb.status))
    if reply_text:
        db.add(FeedbackEvent(feedback_id=fb.id, kind="reply", body=reply_text))

    # 状态变更 或 有新回复 → 通知提交人（一条反馈共用一条通知，更新到最新）
    if (status_changed or reply_text) and fb.user_id is not None:
        await _notify_user_update(db, fb, status_changed=status_changed, reply=reply_text)

    await db.flush()
    return fb


async def get_thread(db: AsyncSession, *, feedback_id: str, user_id: str) -> tuple[Feedback, list[FeedbackEvent]]:
    """用户视角的反馈线程：反馈本体 + 时间线事件。按归属收紧（只能看自己的）。"""
    fb = await db.get(Feedback, feedback_id)
    if fb is None or fb.user_id != user_id:
        raise AppError(40401, "反馈不存在", status_code=404)
    events = (
        await db.execute(
            select(FeedbackEvent)
            .where(FeedbackEvent.feedback_id == feedback_id)
            .order_by(FeedbackEvent.created_at.asc())
        )
    ).scalars().all()
    return fb, list(events)


async def _notify_user_update(
    db: AsyncSession, fb: Feedback, *, status_changed: bool, reply: str
) -> None:
    """一条反馈共用一条通知：每次进展更新这条通知到最新快照、顶起、重置未读。

    body 反映「当前状态 + 最近一次回复」的一致快照，而非单次事件，
    这样无论由状态变更还是回复触发，用户看到的都是该反馈的最新全貌。
    """
    label = _CATEGORY_LABEL.get(fb.category, "反馈")
    lines = [f"当前状态：{_STATUS_LABEL.get(fb.status, fb.status)}"]
    if fb.reply:
        lines.append(f"管理员回复：{fb.reply}")
    await ns.upsert_thread(
        db,
        user_id=fb.user_id,
        type="feedback_update",
        thread_key="feedback_id",
        title=f"你的{label}有新进展",
        body="\n\n".join(lines),
        payload={"feedback_id": fb.id, "status": fb.status},
    )
