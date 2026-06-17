"""注册放量闸门核心逻辑（DB-backed, SQLite）。"""
import pytest

from middleware.error_handler import AppError
from models.user import User
from services import system_config_service as svc


async def _mk_user(db) -> User:
    user = User(nickname="u")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_open_mode_allows(db):
    await svc.update_signup_config(db, admin_id="a", signup_mode="open")
    await db.commit()
    await svc.ensure_signup_allowed(db)  # 不抛即通过


async def test_closed_mode_blocks(db):
    await svc.update_signup_config(db, admin_id="a", signup_mode="closed")
    await db.commit()
    with pytest.raises(AppError) as ei:
        await svc.ensure_signup_allowed(db)
    assert ei.value.code == 40310


async def test_capped_allows_until_full(db):
    # 开新一批：cap=1，起点=now
    await svc.update_signup_config(
        db, admin_id="a", signup_mode="capped", signup_cap=1, start_new_batch=True
    )
    await db.commit()

    # 本批还没新账号 → 放行
    await svc.ensure_signup_allowed(db)

    # 建一个账号后达到 cap → 拦截
    await _mk_user(db)
    with pytest.raises(AppError) as ei:
        await svc.ensure_signup_allowed(db)
    assert ei.value.code == 40311


async def test_start_new_batch_resets_count(db):
    await svc.update_signup_config(
        db, admin_id="a", signup_mode="capped", signup_cap=1, start_new_batch=True
    )
    await db.commit()
    await _mk_user(db)  # 占满本批

    with pytest.raises(AppError):
        await svc.ensure_signup_allowed(db)

    # 开新一批 → 计数清零，又能放行
    await svc.update_signup_config(db, admin_id="a", start_new_batch=True)
    await db.commit()
    await svc.ensure_signup_allowed(db)

    status = await svc.signup_status(db)
    assert status["batch_used"] == 0
    assert status["batch_remaining"] == 1


async def test_capped_without_batch_start_blocks(db):
    # 直接落库一个 capped 但没起点的配置（绕过 service 的自动起点），应视为未开放
    cfg = await svc.get_config(db)
    cfg.signup_mode = "capped"
    cfg.signup_cap = 10
    cfg.signup_batch_start = None
    await db.commit()
    with pytest.raises(AppError) as ei:
        await svc.ensure_signup_allowed(db)
    assert ei.value.code == 40310
