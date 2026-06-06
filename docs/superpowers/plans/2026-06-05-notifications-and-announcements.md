# 通知 + 系统公告 实现计划

> **For agentic workers:** 用 superpowers:executing-plans 或 subagent-driven-development 逐任务执行。步骤用 `- [ ]` 跟踪。

**Goal:** 给 InkWild 补齐个人通知（注册送积分 / 审核通过驳回 / 强制下架 / 积分不足）+ 系统公告（admin 广播），主站铃铛弹窗呈现，admin 后台管理公告。

**Architecture:** 双表分离——个人通知一人一行（`notifications`）；公告一条一行（`announcements`）+ 轻量已读 join 表（`announcement_reads`）。轮询单一 `summary` 端点拿未读数。两个小而专的 service。

**Tech Stack:** 后端 FastAPI + SQLAlchemy 2.0 async + Alembic + pytest；前端 Next 16 + TanStack Query + Radix Popover + vaul Drawer + next-intl；admin-frontend 独立 Next。

参考 spec：`docs/superpowers/specs/2026-06-05-notifications-and-announcements-design.md`

---

## 执行约定（重要）

- **本仓库处于 0-commit hold 状态**（全项目尚未提交）。下面每个任务的 commit 步骤**默认跳过**——按任务「跑通 + 验证」即可；是否真正 `git commit` 由用户最后统一决定。
- 后端测试在 Docker 容器内跑：`docker exec talealive-backend-1 python -m pytest tests/<file> -v`（裸机 venv 亦可：`cd backend && python -m pytest`）。验证只看你新增/改动文件相关的用例是否绿（全量 pytest 有约 56 个 pre-existing 失败，无关）。
- 前端若跑 Docker，加依赖需宿主 + `docker exec talealive-frontend-1` 两边装；本计划不新增依赖。
- 改完前端没反应时重启 frontend 容器。

---

## Phase 1 — 后端数据 + 服务（核心，TDD）

### Task 1: 数据模型

**Files:**
- Create: `backend/models/notification.py`
- Modify: `backend/models/__init__.py`（导出 `Notification` / `Announcement` / `AnnouncementRead`）

- [ ] **Step 1: 写模型**

```python
# backend/models/notification.py
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base  # 跟随现有 import 风格，确认 Base 实际位置
from utils.time import utcnow  # 确认现有 utcnow 来源（user.py 用了 utcnow）


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "read_at"),
        Index("idx_notifications_user_created", "user_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (Index("idx_announcements_status_pub", "status", "published_at"),)
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(16), default="info")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AnnouncementRead(Base):
    __tablename__ = "announcement_reads"
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    announcement_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("announcements.id"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(default=utcnow)
```

注意：**先打开 `backend/models/user.py` 确认 `Base` 与 `utcnow` 的真实 import 路径**，照抄那套（不要臆造 `models.base` / `utils.time`）。

- [ ] **Step 2: 导出** — 在 `backend/models/__init__.py` 加 `from models.notification import Notification, Announcement, AnnouncementRead` 并加入 `__all__`（跟随现有写法）。

- [ ] **Step 3: 验证 import 不炸** — `docker exec talealive-backend-1 python -c "import models; print(models.Notification, models.Announcement, models.AnnouncementRead)"`，期望打印三个类。

---

### Task 2: Alembic 迁移

**Files:**
- Create: `backend/migrations/versions/<rev>_add_notifications_and_announcements.py`

- [ ] **Step 1: 自动生成** — `docker exec talealive-backend-1 alembic revision --autogenerate -m "add notifications and announcements"`。
- [ ] **Step 2: 人工核对** 生成的迁移：三张表 + 索引齐全；`down_revision` 指向当前 head；JSON 列、复合主键正确。若 autogenerate 漏了索引手动补。
- [ ] **Step 3: 升级** — `docker exec talealive-backend-1 alembic upgrade head`，期望无错。
- [ ] **Step 4: 验证表存在** — `docker exec talealive-backend-1 python -c "..."` 或连库 `\d notifications`，确认三表与索引。

---

### Task 3: notification_service（TDD 核心逻辑）

**Files:**
- Create: `backend/services/notification_service.py`
- Test: `backend/tests/test_notification_service.py`

> 注：测试 conftest 只覆盖 `dependencies.get_db`；service 直接收 `db` session 参数，测试用 fixture session 即可。参考现有 `tests/` 里 service 级测试的 session fixture 用法。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_notification_service.py
import pytest
from services import notification_service as ns

@pytest.mark.asyncio
async def test_notify_and_unread_count(db_session, sample_user):
    await ns.notify(db_session, user_id=sample_user.id, type="signup_grant", title="欢迎")
    await db_session.commit()
    assert await ns.unread_count(db_session, user_id=sample_user.id) == 1

@pytest.mark.asyncio
async def test_mark_read_is_ownership_scoped(db_session, sample_user, other_user):
    n = await ns.notify(db_session, user_id=sample_user.id, type="review_approved", title="过审")
    await db_session.commit()
    # 别人不能标记我的通知已读
    await ns.mark_read(db_session, user_id=other_user.id, notification_id=n.id)
    await db_session.commit()
    assert await ns.unread_count(db_session, user_id=sample_user.id) == 1
    await ns.mark_read(db_session, user_id=sample_user.id, notification_id=n.id)
    await db_session.commit()
    assert await ns.unread_count(db_session, user_id=sample_user.id) == 0

@pytest.mark.asyncio
async def test_low_credit_dedup(db_session, sample_user):
    a = await ns.notify_low_credit_once(db_session, user_id=sample_user.id, balance_units=10)
    await db_session.commit()
    b = await ns.notify_low_credit_once(db_session, user_id=sample_user.id, balance_units=8)
    await db_session.commit()
    assert a is not None and b is None  # 已有未读 low_credit 时不再发
    assert await ns.unread_count(db_session, user_id=sample_user.id) == 1
```

> `db_session` / `sample_user` / `other_user` fixture：复用现有 conftest；若无 `other_user`，在测试文件内或 conftest 加一个第二用户 fixture（仿照 `sample_user`）。

- [ ] **Step 2: 跑测试确认失败** — `docker exec talealive-backend-1 python -m pytest tests/test_notification_service.py -v`，期望 ImportError / AttributeError。

- [ ] **Step 3: 实现 service**

```python
# backend/services/notification_service.py
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import Notification
from utils.time import utcnow  # 同 Task1 确认真实路径


async def notify(db, *, user_id, type, title, body=None, link=None, payload=None) -> Notification:
    n = Notification(user_id=user_id, type=type, title=title, body=body, link=link, payload=payload)
    db.add(n)
    await db.flush()  # 不 commit，跟随调用方事务
    return n


async def unread_count(db, *, user_id) -> int:
    return (await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )).scalar_one()


async def list_for_user(db, *, user_id, limit=20, before: datetime | None = None):
    q = select(Notification).where(Notification.user_id == user_id)
    if before is not None:
        q = q.where(Notification.created_at < before)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def mark_read(db, *, user_id, notification_id) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id,
               Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )


async def mark_all_read(db, *, user_id) -> int:
    res = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    return res.rowcount or 0


async def notify_low_credit_once(db, *, user_id, balance_units) -> Notification | None:
    existing = (await db.execute(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.type == "low_credit",
            Notification.read_at.is_(None),
        ).limit(1)
    )).first()
    if existing is not None:
        return None
    return await notify(
        db, user_id=user_id, type="low_credit",
        title="积分余额不足", body="你的积分余额偏低，充值后可继续游玩。",
        link="/me", payload={"balance_units": balance_units},
    )
```

- [ ] **Step 4: 跑测试确认通过** — `docker exec talealive-backend-1 python -m pytest tests/test_notification_service.py -v`，期望 3 绿。

---

### Task 4: announcement_service（TDD：未读规则）

**Files:**
- Create: `backend/services/announcement_service.py`
- Test: `backend/tests/test_announcement_service.py`

- [ ] **Step 1: 写失败测试**（覆盖三条规则：已读 join、新用户不被旧公告刷屏、过期不计未读）

```python
# backend/tests/test_announcement_service.py
from datetime import timedelta
import pytest
from services import announcement_service as anns
from utils.time import utcnow

@pytest.mark.asyncio
async def test_published_counts_as_unread_until_read(db_session, sample_user, admin_user):
    a = await anns.create(db_session, created_by=admin_user.id, title="维护", body="今晚维护")
    await anns.publish(db_session, announcement_id=a.id)
    await db_session.commit()
    uc = await anns.unread_count(db_session, user_id=sample_user.id, user_created_at=sample_user.created_at)
    assert uc == 1
    await anns.mark_read(db_session, user_id=sample_user.id, announcement_id=a.id)
    await db_session.commit()
    assert await anns.unread_count(db_session, user_id=sample_user.id, user_created_at=sample_user.created_at) == 0

@pytest.mark.asyncio
async def test_announcement_before_signup_not_unread_but_listed(db_session, sample_user, admin_user):
    a = await anns.create(db_session, created_by=admin_user.id, title="旧公告", body="历史")
    await anns.publish(db_session, announcement_id=a.id)
    # 强制 published_at 早于用户注册时间
    a.published_at = sample_user.created_at - timedelta(days=1)
    await db_session.commit()
    assert await anns.unread_count(db_session, user_id=sample_user.id, user_created_at=sample_user.created_at) == 0
    rows = await anns.list_for_user(db_session, user_id=sample_user.id, user_created_at=sample_user.created_at)
    assert any(ann.id == a.id for ann, _read in rows)  # 列表仍可见

@pytest.mark.asyncio
async def test_expired_not_unread(db_session, sample_user, admin_user):
    a = await anns.create(db_session, created_by=admin_user.id, title="过期", body="x",
                          expires_at=utcnow() - timedelta(hours=1))
    await anns.publish(db_session, announcement_id=a.id)
    await db_session.commit()
    assert await anns.unread_count(db_session, user_id=sample_user.id, user_created_at=sample_user.created_at) == 0
```

> `admin_user` fixture：若 conftest 无，加一个 `is_admin=True` 用户 fixture。

- [ ] **Step 2: 跑测试确认失败**。

- [ ] **Step 3: 实现 service**

```python
# backend/services/announcement_service.py
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import Announcement, AnnouncementRead
from utils.time import utcnow


def _visible_published(now: datetime):
    return and_(
        Announcement.status == "published",
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
    )


async def create(db, *, created_by, title, body, level="info", expires_at=None) -> Announcement:
    a = Announcement(created_by=created_by, title=title, body=body, level=level,
                     status="draft", expires_at=expires_at)
    db.add(a)
    await db.flush()
    return a


async def update(db, *, announcement_id, **fields) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise ValueError("公告不存在")
    for k, v in fields.items():
        if v is not None:
            setattr(a, k, v)
    await db.flush()
    return a


async def publish(db, *, announcement_id) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise ValueError("公告不存在")
    a.status = "published"
    a.published_at = utcnow()
    await db.flush()
    return a


async def unpublish(db, *, announcement_id) -> Announcement:
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise ValueError("公告不存在")
    a.status = "draft"
    await db.flush()
    return a


async def unread_count(db, *, user_id, user_created_at) -> int:
    now = utcnow()
    read_sub = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user_id)
    return (await db.execute(
        select(func.count()).select_from(Announcement).where(
            _visible_published(now),
            Announcement.published_at >= user_created_at,
            Announcement.id.notin_(read_sub),
        )
    )).scalar_one()


async def list_for_user(db, *, user_id, user_created_at, limit=20, before=None):
    now = utcnow()
    q = select(Announcement, AnnouncementRead.read_at).outerjoin(
        AnnouncementRead,
        and_(AnnouncementRead.announcement_id == Announcement.id,
             AnnouncementRead.user_id == user_id),
    ).where(_visible_published(now))
    if before is not None:
        q = q.where(Announcement.published_at < before)
    q = q.order_by(Announcement.published_at.desc()).limit(limit)
    rows = (await db.execute(q)).all()
    return [(ann, read_at is not None) for ann, read_at in rows]


async def mark_read(db, *, user_id, announcement_id) -> None:
    stmt = pg_insert(AnnouncementRead).values(
        user_id=user_id, announcement_id=announcement_id, read_at=utcnow()
    ).on_conflict_do_nothing(index_elements=["user_id", "announcement_id"])
    await db.execute(stmt)


async def mark_all_read(db, *, user_id, user_created_at) -> int:
    now = utcnow()
    read_sub = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user_id)
    ids = (await db.execute(
        select(Announcement.id).where(_visible_published(now), Announcement.id.notin_(read_sub))
    )).scalars().all()
    for aid in ids:
        await mark_read(db, user_id=user_id, announcement_id=aid)
    return len(ids)


async def list_all(db, *, limit=50, offset=0):
    q = select(Announcement).order_by(Announcement.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(q)).scalars().all())
```

> 注：`list_for_user` 不加 `published_at >= user_created_at` 过滤（历史公告仍可见，符合 spec），只有 `unread_count` 加该过滤。

- [ ] **Step 4: 跑测试确认通过** — 3 绿。

---

## Phase 2 — 后端 API + 触发点

### Task 5: schemas

**Files:**
- Create: `backend/schemas/notification.py`

- [ ] **Step 1:** 写 Pydantic（跟随 `schemas/` 现有风格，`model_config = ConfigDict(from_attributes=True)` 等）：

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    title: str
    body: str | None
    link: str | None
    payload: dict | None
    read_at: datetime | None
    created_at: datetime

class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    next_before: datetime | None

class AnnouncementOut(BaseModel):
    id: str
    title: str
    body: str
    level: str
    published_at: datetime | None
    read: bool

class AnnouncementListOut(BaseModel):
    items: list[AnnouncementOut]
    next_before: datetime | None

class NotificationSummaryOut(BaseModel):
    notifications: int
    announcements: int

# admin
class AnnouncementCreateIn(BaseModel):
    title: str
    body: str
    level: str = "info"
    expires_at: datetime | None = None

class AnnouncementUpdateIn(BaseModel):
    title: str | None = None
    body: str | None = None
    level: str | None = None
    expires_at: datetime | None = None

class AnnouncementAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    body: str
    level: str
    status: str
    published_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
```

- [ ] **Step 2:** import 验证不炸。

---

### Task 6: 用户端 API `api/notifications.py`

**Files:**
- Create: `backend/api/notifications.py`
- Modify: `backend/main.py`（import + `include_router`）

- [ ] **Step 1: 写路由**（用 `get_current_user`、`get_db`，统一 `{"code":0,"data":...,"message":"ok"}` 包裹）。端点：
  - `GET /api/notifications/summary` → `NotificationSummaryOut`（调 `ns.unread_count` + `anns.unread_count`，后者传 `user.created_at`）。
  - `GET /api/notifications?limit&before` → `NotificationListOut`（`next_before` = 返回最后一条 created_at，不足 limit 则 None）。
  - `POST /api/notifications/{id}/read` → 调 `ns.mark_read` + commit。
  - `POST /api/notifications/read-all` → 调 `ns.mark_all_read` + commit。
  - `GET /api/announcements?limit&before` → `AnnouncementListOut`（把 `(ann, read)` 映射成 `AnnouncementOut`）。
  - `POST /api/announcements/{id}/read`、`POST /api/announcements/read-all`（传 `user.created_at`）+ commit。

  > **从 `dependencies` import `get_db`**（conftest 只覆盖它），不要从 database 直接 import，否则测试连真库。

```python
# backend/api/notifications.py  —— 结构骨架
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from dependencies import get_current_user, get_db
from models.user import User
from schemas.notification import (NotificationListOut, NotificationOut, NotificationSummaryOut,
                                  AnnouncementListOut, AnnouncementOut)
from services import notification_service as ns, announcement_service as anns

router = APIRouter(prefix="/api", tags=["notifications"])

def _ok(data): return {"code": 0, "data": data, "message": "ok"}

@router.get("/notifications/summary")
async def summary(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    n = await ns.unread_count(db, user_id=user.id)
    m = await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at)
    return _ok(NotificationSummaryOut(notifications=n, announcements=m).model_dump())

@router.get("/notifications")
async def list_notifications(limit: int = Query(20, le=50), before: datetime | None = None,
                             user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await ns.list_for_user(db, user_id=user.id, limit=limit, before=before)
    next_before = rows[-1].created_at if len(rows) == limit else None
    return _ok(NotificationListOut(
        items=[NotificationOut.model_validate(r) for r in rows], next_before=next_before).model_dump())

# ... read / read-all / announcements 同构，按上面清单补全
```

- [ ] **Step 2: 注册** — `main.py` 加 `from api.notifications import router as notifications_router` + `app.include_router(notifications_router)`。
- [ ] **Step 3: 冒烟** — 重启 backend 容器，登录态 `curl` 或浏览器打 `/api/notifications/summary`，期望 `{"code":0,"data":{"notifications":0,"announcements":0}...}`。

---

### Task 7: Admin 端 API `api/admin_announcements.py`

**Files:**
- Create: `backend/api/admin_announcements.py`
- Modify: `backend/main.py`

- [ ] **Step 1: 写路由**（`get_current_admin_user`，每个写操作 `record_admin_action` + `db.commit()`，仿 `admin_review.py` 的 `_client_ip/_ua` + audit 写法）：
  - `GET /api/admin/announcements?limit&offset` → `anns.list_all` → `AnnouncementAdminOut` 列表。
  - `POST /api/admin/announcements`（`AnnouncementCreateIn`）→ `anns.create` + audit `announcement.create`。
  - `PATCH /api/admin/announcements/{id}`（`AnnouncementUpdateIn`）→ `anns.update` + audit。
  - `POST /api/admin/announcements/{id}/publish` → `anns.publish` + audit `announcement.publish`。
  - `POST /api/admin/announcements/{id}/unpublish` → `anns.unpublish` + audit。
  - `ValueError` → `HTTPException(400)`。

- [ ] **Step 2: 注册** main.py（放 admin 路由那一组）。
- [ ] **Step 3: 冒烟** — admin 登录态 `POST` 建一条 → `publish` → 用户端 `GET /api/announcements` 能看到。

---

### Task 8: 接通触发点

**Files:**
- Modify: `backend/services/credit_service.py`（signup grant + low_credit）
- Modify: `backend/api/admin_review.py`（approve/reject）
- Modify: `backend/services/publish_service.py`（admin 强制下架）
- Test: `backend/tests/test_notification_triggers.py`（轻量）

- [ ] **Step 1: signup 通知** — `credit_service.get_or_create_wallet` 里，在 `db.add(CreditLedger(...))` 之后、`await db.commit()` 之前插：

```python
from services import notification_service as ns
await ns.notify(
    db, user_id=user_id, type="signup_grant",
    title="欢迎加入 InkWild",
    body=f"已为你送上 {grant_units // 100} 积分，开始你的第一段故事吧。",  # 确认 CREDIT_UNIT_SCALE=100 换算
    link="/discover", payload={"units": grant_units},
)
```
（确认 `CREDIT_UNIT_SCALE` 的换算关系再定 body 文案；import 放函数内或文件顶，避免循环 import——credit_service ← notification_service 无环，可顶层 import。）

- [ ] **Step 2: low_credit 通知** — 找到 `credit_service` 中 settle/charge 扣减余额、已知 `balance_after_units` 的位置，在余额低于阈值时调用：

```python
LOW_CREDIT_THRESHOLD_UNITS = 100 * CREDIT_UNIT_SCALE  # 约等于「一局成本」量级，取整百积分
if balance_after_units < LOW_CREDIT_THRESHOLD_UNITS:
    await ns.notify_low_credit_once(db, user_id=user_id, balance_units=balance_after_units)
```
插在该路径已有事务内（settle 通常会 commit，确保 notify 在同一 commit 前）。

- [ ] **Step 3: 审核 approve/reject 通知** — 在 `admin_review.py` 两个端点 `record_admin_action` 之后、`await db.commit()` 之前：

```python
from sqlalchemy import select
from models.draft import WorldDraft, ScriptDraft
from services import notification_service as ns

# approve 分支：拿 draft 的作者
DraftModel = WorldDraft if kind == "world" else ScriptDraft
draft_row = (await db.execute(select(DraftModel).where(DraftModel.id == draft_id))).scalar_one_or_none()
if draft_row is not None:
    title_text = getattr(obj, "title", "你的作品")
    await ns.notify(db, user_id=draft_row.created_by_user_id, type="review_approved",
                    title=f"《{title_text}》已通过审核",
                    body="你的内容已发布，现在所有人都能体验了。",
                    link=f"/{'worlds' if kind=='world' else 'play'}/{obj.id}",  # link 取合理深链
                    payload={"kind": kind, "draft_id": draft_id, "target_id": str(obj.id)})

# reject 分支：reject_* 已返回 draft 对象
await ns.notify(db, user_id=draft.created_by_user_id, type="review_rejected",
                title="作品未通过审核",
                body=(payload.note or "请根据审核意见修改后重新提交。"),
                link="/workshop",  # 指回创作工坊
                payload={"kind": kind, "draft_id": draft_id, "note": payload.note})
```

- [ ] **Step 4: 强制下架通知** — `publish_service.withdraw_world` / `withdraw_script`，在 `by_admin=True` 分支里（拿到 world/script 的 `created_by_user_id` 与 title）调 `ns.notify(type="content_takedown", ...)`，link 指 `/workshop`。确认这两个函数能拿到作者 id（worlds/scripts 有 `created_by_user_id`，见迁移 c45bcbdcd049）。

- [ ] **Step 5: 触发测试**（轻量，验证「埋点接通」）

```python
# backend/tests/test_notification_triggers.py
# 直接调 credit_service.get_or_create_wallet(新用户) → 断言该用户有一条 type=signup_grant 未读通知
# （审核触发走 API 层，端到端较重，可只测 signup 这条最易隔离的；其余靠冒烟）
```

- [ ] **Step 6: 跑** signup 触发测试 + 已有 credit 相关测试，确认没回归。

---

## Phase 3 — 前端主站（简洁为主）

### Task 9: 数据层 `lib/notifications.ts`

**Files:**
- Create: `frontend/lib/notifications.ts`
- Test: `frontend/lib/notifications.test.ts`（一个轻量 vitest）

- [ ] **Step 1:** 类型 + API 封装（用现有 `apiFetch`，确认其签名/返回解包方式，仿 `lib/` 现有 client）：

```ts
export type NotificationItem = {
  id: string; type: string; title: string; body: string | null;
  link: string | null; payload: Record<string, unknown> | null;
  read_at: string | null; created_at: string;
};
export type AnnouncementItem = {
  id: string; title: string; body: string; level: "info" | "warning" | "critical";
  published_at: string | null; read: boolean;
};
export type NotificationSummary = { notifications: number; announcements: number };

export async function fetchSummary(): Promise<NotificationSummary> { /* GET /api/notifications/summary */ }
export async function fetchNotifications(before?: string): Promise<{items: NotificationItem[]; next_before: string|null}> {}
export async function fetchAnnouncements(before?: string): Promise<{items: AnnouncementItem[]; next_before: string|null}> {}
export async function markNotificationRead(id: string): Promise<void> {}
export async function markAllNotificationsRead(): Promise<void> {}
export async function markAnnouncementRead(id: string): Promise<void> {}
export async function markAllAnnouncementsRead(): Promise<void> {}

export const totalUnread = (s: NotificationSummary) => s.notifications + s.announcements;
```

- [ ] **Step 2:** TanStack Query hooks（同文件或 `hooks` 旁置，跟随项目约定）：

```ts
export function useNotificationSummary(enabled: boolean) {
  return useQuery({ queryKey: ["notif-summary"], queryFn: fetchSummary,
    enabled, refetchInterval: 45_000, refetchOnWindowFocus: true });
}
export function useNotifications(enabled: boolean) { /* useInfiniteQuery by next_before */ }
export function useAnnouncements(enabled: boolean) { /* 同上 */ }
// useMarkRead / useMarkAllRead：mutation，onSuccess invalidate ["notif-summary"] + 对应列表
```

- [ ] **Step 3:** vitest — 测 `totalUnread` 合并逻辑 + summary 解析（mock fetch 返回包裹体，断言解包正确）。`npm run test -- notifications`，期望绿。

---

### Task 10: 铃铛 + 面板组件

**Files:**
- Create: `frontend/components/NotificationBell.tsx`
- Create: `frontend/components/notifications/NotificationPanel.tsx`
- Create: `frontend/components/notifications/NotificationItem.tsx`
- Create: `frontend/components/notifications/AnnouncementItem.tsx`

- [ ] **Step 1: NotificationBell** — `"use client"`。读 auth store 判断登录（未登录返回 null）。`useNotificationSummary(isLoggedIn)` 拿未读数 → 铃铛右上角红点/数字（>0 才显示，>99 显示 99+）。桌面用 Radix `Popover`（项目已有 @radix-ui）包 `NotificationPanel`；移动用 vaul `Drawer`。用 `useMediaQuery`/断点（项目 768/769 约定）选其一，或两个都渲染按 CSS 显隐——跟随项目现有 Popover/Drawer 用例。图标用项目已用的 icon 库（ProductNav 用了 lucide：`Bell`）。

- [ ] **Step 2: NotificationPanel** — 顶部两 tab（`通知` / `系统公告`，各带未读小数字）。tab 切换用本地 state。各 tab 内容：
  - 通知 tab：`useNotifications` 列表 → `NotificationItem`；底部「全部已读」按钮（`useMarkAllRead`）。
  - 公告 tab：`useAnnouncements` → `AnnouncementItem`；底部「全部已读」。
  - 空态：居中浅色文案（i18n）。
  - 「加载更多」按钮（有 next_before 才显示）。
  - 面板宽度桌面约 360–400px，移动 Drawer 占底部 ~80dvh。

- [ ] **Step 3: NotificationItem** — 标题（未读加粗/前置小圆点）+ body 一行截断 + 相对时间（用项目现有时间格式化，或 `Intl.RelativeTimeFormat`）。点击：若 `read_at==null` 触发 `markNotificationRead`（乐观）；有 `link` 则 `router.push(link)` 并关闭面板。

- [ ] **Step 4: AnnouncementItem** — 左侧按 `level` 配色竖条（info=银雾/warning=琥珀/critical=红，用 `var(--lv-*)` 就近取色）+ 标题 + body 截断 + 时间。点击标记已读 + 展开/或直接展示 body。

- [ ] **Step 5:** 视觉走 v2.3：`.lv-t-*` 字号、`var(--lv-accent)` 角标、`var(--lv-ink)`/`--lv-bg` 等，触摸目标 ≥44px。**不写** inline `text-[Xrem]`、不引旧 token。

- [ ] **Step 6: 验证** — `cd frontend && npm run build` 通过（tsc 不报错）。

---

### Task 11: 挂载 + i18n

**Files:**
- Modify: `frontend/components/ProductNav.tsx`（右侧区插 `<NotificationBell />`）
- Modify: `frontend/components/MobileTopBar.tsx`（`right` 槽：`<><NotificationBell /><CreditBalanceChip /></>`）
- Modify: `frontend/i18n/zh.json`、`frontend/i18n/en.json`（加 `notifications.*`：tab 标题、空态、全部已读、加载更多、各 type 兜底文案等）

- [ ] **Step 1:** ProductNav 右侧（LangChip/CreditBalanceChip 同一 flex 容器）加铃铛，注意 z-index 让 Popover 浮在 nav scrim 之上。
- [ ] **Step 2:** MobileTopBar 默认 `resolvedRight` 在登录态改为铃铛 + 余额并排（仍未登录则不显示铃铛）。
- [ ] **Step 3:** i18n key 双语补齐；组件内文案全部走 `t('notifications.xxx')`。
- [ ] **Step 4: 真机验证（用户）** — 起前端，登录态：铃铛出现、有未读时角标、点开两 tab 列表正常、标记已读后角标减少、移动端 Drawer 正常。后端先手动 `INSERT` 或建几条公告造数据。

---

## Phase 4 — Admin 前端

### Task 12: 公告管理页

**Files:**
- Create: admin-frontend 下公告管理页（路由 + 组件，沿 admin-frontend 现有页面结构，如 `app/(dashboard)/announcements/`）
- Modify: admin-frontend 侧边导航加入口

- [ ] **Step 1:** 列表页：表格（标题 / level / 状态 / 发布时间 / 操作）。调 `GET /api/admin/announcements`。沿用 admin-frontend 现有 fetch 封装与视觉。
- [ ] **Step 2:** 新建/编辑表单（标题、正文 textarea、level select、过期时间可选）→ `POST` / `PATCH`。
- [ ] **Step 3:** 行内「发布 / 下架」按钮 → 对应端点，操作后刷新列表。
- [ ] **Step 4: 验证（用户）** — admin 后台建公告 → 发布 → 主站铃铛公告 tab 出现；下架后消失。

---

## Self-Review 结论

- **Spec 覆盖：** §3 数据模型→Task1/2；§4 服务→Task3/4；§5 触发点→Task8；§6 API→Task6/7；§7 schemas→Task5；§8 前端→Task9/10/11；§9 admin→Task12；§10 测试→Task3/4/8/9 内嵌。无遗漏。
- **类型一致：** service 函数名（`notify`/`unread_count`/`mark_read`/`mark_all_read`/`notify_low_credit_once`；`create`/`publish`/`unpublish`/`list_for_user`/`list_all`）在各 Task 间一致；schema 字段与 service 返回一致。
- **待执行时确认的真实路径**（计划里标注过）：`Base`/`utcnow` import 来源、`apiFetch` 形态、`CREDIT_UNIT_SCALE` 换算、settle 扣减点、worlds/scripts 是否有 `created_by_user_id`、admin-frontend 页面目录结构。这些在对应 Task 第一步先读现有代码核对，不臆造。
