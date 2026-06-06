"""个人通知 service — 核心路径（DB-backed, SQLite）。"""
from models.user import User
from services import notification_service as ns


async def _mk_user(db) -> str:
    user = User(nickname="n")
    db.add(user)
    await db.commit()
    return user.id


async def test_notify_and_unread_count(db):
    uid = await _mk_user(db)
    await ns.notify(db, user_id=uid, type="signup_grant", title="欢迎")
    await db.commit()
    assert await ns.unread_count(db, user_id=uid) == 1


async def test_mark_read_is_ownership_scoped(db):
    uid = await _mk_user(db)
    other = await _mk_user(db)
    n = await ns.notify(db, user_id=uid, type="review_approved", title="过审")
    await db.commit()

    # 别人不能标记我的通知已读
    await ns.mark_read(db, user_id=other, notification_id=n.id)
    await db.commit()
    assert await ns.unread_count(db, user_id=uid) == 1

    await ns.mark_read(db, user_id=uid, notification_id=n.id)
    await db.commit()
    assert await ns.unread_count(db, user_id=uid) == 0


async def test_mark_all_read(db):
    uid = await _mk_user(db)
    await ns.notify(db, user_id=uid, type="review_approved", title="a")
    await ns.notify(db, user_id=uid, type="review_rejected", title="b")
    await db.commit()
    assert await ns.unread_count(db, user_id=uid) == 2
    affected = await ns.mark_all_read(db, user_id=uid)
    await db.commit()
    assert affected == 2
    assert await ns.unread_count(db, user_id=uid) == 0


async def test_low_credit_dedup(db):
    uid = await _mk_user(db)
    a = await ns.notify_low_credit_once(db, user_id=uid, balance_units=10)
    await db.commit()
    b = await ns.notify_low_credit_once(db, user_id=uid, balance_units=8)
    await db.commit()
    assert a is not None and b is None  # 已有未读 low_credit 时不再发
    assert await ns.unread_count(db, user_id=uid) == 1


async def test_list_for_user_orders_newest_first(db):
    uid = await _mk_user(db)
    await ns.notify(db, user_id=uid, type="review_approved", title="first")
    await ns.notify(db, user_id=uid, type="review_approved", title="second")
    await db.commit()
    rows = await ns.list_for_user(db, user_id=uid, limit=20)
    assert [r.title for r in rows] == ["second", "first"]
