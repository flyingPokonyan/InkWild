"""系统公告 service — 未读规则核心路径（DB-backed, SQLite）。"""
from datetime import timedelta

from models.user import User
from services import announcement_service as anns
from utils import utcnow


async def _mk_user(db, *, is_admin: bool = False) -> User:
    user = User(nickname="a", is_admin=is_admin)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_published_counts_as_unread_until_read(db):
    admin = await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    a = await anns.create(db, created_by=admin.id, title="维护", body="今晚维护")
    await anns.publish(db, announcement_id=a.id)
    await db.commit()

    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 1
    await anns.mark_read(db, user_id=user.id, announcement_id=a.id)
    await db.commit()
    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 0


async def test_announcement_before_signup_not_unread_but_listed(db):
    admin = await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    a = await anns.create(db, created_by=admin.id, title="旧公告", body="历史")
    await anns.publish(db, announcement_id=a.id)
    # 强制 published_at 早于用户注册时间
    a.published_at = user.created_at - timedelta(days=1)
    await db.commit()

    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 0
    rows = await anns.list_for_user(db, user_id=user.id, user_created_at=user.created_at)
    assert any(ann.id == a.id for ann, _read in rows)  # 列表仍可见


async def test_expired_not_unread(db):
    admin = await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    a = await anns.create(
        db, created_by=admin.id, title="过期", body="x", expires_at=utcnow() - timedelta(hours=1)
    )
    await anns.publish(db, announcement_id=a.id)
    await db.commit()
    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 0


async def test_draft_not_visible_or_unread(db):
    admin = await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    a = await anns.create(db, created_by=admin.id, title="草稿", body="未发布")
    await db.commit()
    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 0
    rows = await anns.list_for_user(db, user_id=user.id, user_created_at=user.created_at)
    assert all(ann.id != a.id for ann, _ in rows)
    # admin 视角看得到草稿
    all_rows = await anns.list_all(db)
    assert any(x.id == a.id for x in all_rows)


async def test_unpublish_removes_from_user_view(db):
    admin = await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    a = await anns.create(db, created_by=admin.id, title="临时", body="x")
    await anns.publish(db, announcement_id=a.id)
    await db.commit()
    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 1
    await anns.unpublish(db, announcement_id=a.id)
    await db.commit()
    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 0


async def test_mark_all_read(db):
    admin = await _mk_user(db, is_admin=True)
    user = await _mk_user(db)
    for i in range(3):
        x = await anns.create(db, created_by=admin.id, title=f"t{i}", body="x")
        await anns.publish(db, announcement_id=x.id)
    await db.commit()
    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 3
    n = await anns.mark_all_read(db, user_id=user.id, user_created_at=user.created_at)
    await db.commit()
    assert n == 3
    assert await anns.unread_count(db, user_id=user.id, user_created_at=user.created_at) == 0
