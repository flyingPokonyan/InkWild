"""个人通知 service。

通知一人一行，由系统在事件点（注册送积分 / 审核结果 / 强制下架 / 积分不足）
自动产生。`notify` 不自己 commit —— 跟随调用方所在事务，与触发事件同事务提交。
"""
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import Notification
from utils import utcnow


async def notify(
    db: AsyncSession,
    *,
    user_id: str,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    payload: dict | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id, type=type, title=title, body=body, link=link, payload=payload
    )
    db.add(n)
    await db.flush()
    return n


async def unread_count(db: AsyncSession, *, user_id: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
    ).scalar_one()


async def list_for_user(
    db: AsyncSession, *, user_id: str, limit: int = 20, before: datetime | None = None
) -> list[Notification]:
    q = select(Notification).where(Notification.user_id == user_id)
    if before is not None:
        q = q.where(Notification.created_at < before)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def mark_read(db: AsyncSession, *, user_id: str, notification_id: str) -> None:
    """标记单条已读，按归属收紧（别人无法标记我的通知）。"""
    await db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=utcnow())
    )


async def mark_all_read(db: AsyncSession, *, user_id: str) -> int:
    res = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    return res.rowcount or 0


async def notify_low_credit_once(
    db: AsyncSession, *, user_id: str, balance_units: int
) -> Notification | None:
    """积分不足通知，带去重：已有未读 low_credit 时不再发，避免每回合刷屏。"""
    existing = (
        await db.execute(
            select(Notification.id)
            .where(
                Notification.user_id == user_id,
                Notification.type == "low_credit",
                Notification.read_at.is_(None),
            )
            .limit(1)
        )
    ).first()
    if existing is not None:
        return None
    return await notify(
        db,
        user_id=user_id,
        type="low_credit",
        title="积分余额不足",
        body="你的积分余额偏低，充值后可继续游玩。",
        link="/me",
        payload={"balance_units": balance_units},
    )
