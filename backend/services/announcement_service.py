"""系统公告 service。

公告一条一行，admin 创建并发布，发给全体用户。已读用轻量 join 表
`announcement_reads` 记录（读了才写一行），不做扇出。

未读判定：已发布 且未过期 且 `published_at >= user.created_at`（新用户不被注册前
的历史公告刷屏）且当前用户无 read 行。列表 `list_for_user` 不加 `published_at`
下限——历史公告仍可见（按已读展示），只有未读计数收紧。
"""
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import Announcement, AnnouncementRead
from utils import utcnow


def _visible_published(now: datetime):
    return and_(
        Announcement.status == "published",
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
    )


# ---------- admin 写 ----------

async def create(
    db: AsyncSession,
    *,
    created_by: str,
    title: str,
    body: str,
    level: str = "info",
    image_url: str | None = None,
    expires_at: datetime | None = None,
) -> Announcement:
    a = Announcement(
        created_by=created_by, title=title, body=body, level=level,
        image_url=image_url, status="draft", expires_at=expires_at,
    )
    db.add(a)
    await db.flush()
    return a


async def update(db: AsyncSession, *, announcement_id: str, **fields) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise ValueError("公告不存在")
    for key, value in fields.items():
        if value is not None:
            setattr(a, key, value)
    await db.flush()
    return a


async def publish(db: AsyncSession, *, announcement_id: str) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise ValueError("公告不存在")
    a.status = "published"
    a.published_at = utcnow()
    await db.flush()
    return a


async def unpublish(db: AsyncSession, *, announcement_id: str) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise ValueError("公告不存在")
    a.status = "draft"
    await db.flush()
    return a


async def list_all(db: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[Announcement]:
    q = select(Announcement).order_by(Announcement.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(q)).scalars().all())


# ---------- 用户视角 ----------

async def unread_count(db: AsyncSession, *, user_id: str, user_created_at: datetime) -> int:
    now = utcnow()
    read_sub = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user_id)
    return (
        await db.execute(
            select(func.count())
            .select_from(Announcement)
            .where(
                _visible_published(now),
                Announcement.published_at >= user_created_at,
                Announcement.id.notin_(read_sub),
            )
        )
    ).scalar_one()


async def list_for_user(
    db: AsyncSession,
    *,
    user_id: str,
    user_created_at: datetime,
    limit: int = 20,
    before: datetime | None = None,
) -> list[tuple[Announcement, bool]]:
    now = utcnow()
    q = (
        select(Announcement, AnnouncementRead.read_at)
        .outerjoin(
            AnnouncementRead,
            and_(
                AnnouncementRead.announcement_id == Announcement.id,
                AnnouncementRead.user_id == user_id,
            ),
        )
        .where(_visible_published(now))
    )
    if before is not None:
        q = q.where(Announcement.published_at < before)
    q = q.order_by(Announcement.published_at.desc()).limit(limit)
    rows = (await db.execute(q)).all()
    return [(ann, read_at is not None) for ann, read_at in rows]


async def mark_read(db: AsyncSession, *, user_id: str, announcement_id: str) -> None:
    """幂等 upsert：用 merge 实现，跨 SQLite/Postgres 可移植。"""
    await db.merge(
        AnnouncementRead(user_id=user_id, announcement_id=announcement_id, read_at=utcnow())
    )


async def mark_all_read(db: AsyncSession, *, user_id: str, user_created_at: datetime) -> int:
    now = utcnow()
    read_sub = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user_id)
    ids = (
        await db.execute(
            select(Announcement.id).where(_visible_published(now), Announcement.id.notin_(read_sub))
        )
    ).scalars().all()
    for aid in ids:
        await mark_read(db, user_id=user_id, announcement_id=aid)
    return len(ids)
