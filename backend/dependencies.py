from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from config import settings
from database import async_session
from middleware.error_handler import AppError
from models.user import User
from services.auth_service import AuthService


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
    auth_session_id: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> User | None:
    if not auth_session_id:
        return None

    service = AuthService()
    return await service.get_user_by_session_id(db, auth_session_id)


async def get_current_user(
    current_user: User | None = Depends(get_current_user_optional),
) -> User:
    if current_user is None:
        raise AppError(40100, "请先登录", status_code=401)
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise AppError(40300, "需要管理员权限", status_code=403)
    return current_user


_redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_pool
