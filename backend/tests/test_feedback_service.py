"""用户反馈 service：创建 + 通知 admin + 状态流转（DB-backed, SQLite）。"""
import pytest

from middleware.error_handler import AppError
from models.user import User
from services import feedback_service as fb
from services import notification_service as ns


async def _mk_user(db, *, is_admin: bool = False) -> User:
    user = User(nickname="u", is_admin=is_admin)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_create_feedback_notifies_admins(db):
    admin = await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    rec = await fb.create(
        db, user_id=user.id, category="bug", content="点开报错", page_url="/play/1"
    )
    await db.commit()
    assert rec.status == "new"
    # admin 收到一条 feedback_new 通知
    assert await ns.unread_count(db, user_id=admin.id) == 1


async def test_create_rejects_unknown_category(db):
    user = await _mk_user(db)
    with pytest.raises(AppError) as ei:
        await fb.create(db, user_id=user.id, category="spam", content="x")
    assert ei.value.code == 42240


async def test_update_status_flow(db):
    await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    rec = await fb.create(db, user_id=user.id, category="suggestion", content="建议加暗黑模式")
    await db.commit()

    await fb.update(db, feedback_id=rec.id, status="triaged", admin_note="已排期")
    await db.commit()
    rows = await fb.list_for_admin(db, status="triaged")
    assert len(rows) == 1
    assert rows[0].admin_note == "已排期"


async def test_status_change_and_reply_notify_submitter(db):
    await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    rec = await fb.create(db, user_id=user.id, category="bug", content="白屏")
    await db.commit()
    before = await ns.unread_count(db, user_id=user.id)

    # 状态变更 + 回复 → 给提交人发一条进度通知
    await fb.update(db, feedback_id=rec.id, status="resolved", admin_note="内部:已修", reply="已修复，请刷新")
    await db.commit()
    assert await ns.unread_count(db, user_id=user.id) == before + 1

    # 内部备注对外不可见、回复对外可见
    assert rec.admin_note == "内部:已修"
    assert rec.reply == "已修复，请刷新"


async def test_multiple_updates_share_one_notification(db):
    """一条反馈共用一条通知：多次进展只更新同一条（顶起+重置未读），不刷屏。"""
    from models.notification import Notification
    from sqlalchemy import select

    await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    rec = await fb.create(db, user_id=user.id, category="bug", content="白屏")
    await db.commit()

    await fb.update(db, feedback_id=rec.id, status="triaged")
    await db.commit()
    await fb.update(db, feedback_id=rec.id, reply="正在排查")
    await db.commit()
    await fb.update(db, feedback_id=rec.id, status="resolved", reply="已修复")
    await db.commit()

    notifs = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == user.id, Notification.type == "feedback_update"
            )
        )
    ).scalars().all()
    assert len(notifs) == 1  # 三次进展只有一条通知
    n = notifs[0]
    assert n.read_at is None  # 仍未读（每次进展重置提醒）
    assert "已解决" in (n.body or "")  # 反映最新状态
    assert "已修复" in (n.body or "")  # 反映最新回复


async def test_no_change_no_notification(db):
    await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    rec = await fb.create(db, user_id=user.id, category="bug", content="x")
    await db.commit()
    before = await ns.unread_count(db, user_id=user.id)
    # 只改内部备注、状态不变、无回复 → 不打扰用户
    await fb.update(db, feedback_id=rec.id, status="new", admin_note="排查中")
    await db.commit()
    assert await ns.unread_count(db, user_id=user.id) == before


async def test_thread_accumulates_timeline(db):
    """解决记录全貌：状态变更 + 每次回复都进时间线，可按归属取出。"""
    await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    rec = await fb.create(db, user_id=user.id, category="bug", content="白屏")
    await db.commit()

    await fb.update(db, feedback_id=rec.id, status="triaged", reply="收到，正在看")
    await db.commit()
    await fb.update(db, feedback_id=rec.id, status="resolved", reply="已修复")
    await db.commit()

    fb_row, events = await fb.get_thread(db, feedback_id=rec.id, user_id=user.id)
    assert fb_row.status == "resolved"
    kinds = [(e.kind, e.status or e.body) for e in events]
    # 时间线按序：状态→处理中、回复、状态→已解决、回复
    assert kinds == [
        ("status", "triaged"),
        ("reply", "收到，正在看"),
        ("status", "resolved"),
        ("reply", "已修复"),
    ]


async def test_thread_ownership_enforced(db):
    user = await _mk_user(db)
    other = await _mk_user(db)
    rec = await fb.create(db, user_id=user.id, category="bug", content="x")
    await db.commit()
    with pytest.raises(AppError) as ei:
        await fb.get_thread(db, feedback_id=rec.id, user_id=other.id)
    assert ei.value.code == 40401


async def test_update_rejects_unknown_status(db):
    user = await _mk_user(db)
    rec = await fb.create(db, user_id=user.id, category="bug", content="x")
    await db.commit()
    with pytest.raises(AppError) as ei:
        await fb.update(db, feedback_id=rec.id, status="wontfix")
    assert ei.value.code == 42241
