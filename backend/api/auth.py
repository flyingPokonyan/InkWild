import base64
import re

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import get_current_user, get_current_user_optional, get_db, get_redis
from middleware.error_handler import AppError
from middleware.rate_limit import RedisTokenBucketRateLimiter
from models.user import AuthIdentity, User
from schemas.auth import (
    ChangePasswordRequest,
    CurrentUserDTO,
    ForgotPasswordRequest,
    IdentitySummaryDTO,
    PasswordLoginRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
    UploadAvatarRequest,
    VerifyEmailRequest,
)
from services.auth_service import AuthService, hash_password, normalize_email, verify_password
from services.image_storage import get_image_storage, make_image_key
from services.oauth_service import (
    SUPPORTED_PROVIDERS,
    normalize_profile,
    oauth,
    upsert_oauth_identity,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
dev_router = APIRouter(prefix="/api/dev", tags=["dev-auth"])


def _auth_service() -> AuthService:
    return AuthService()


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
        max_age=settings.web_session_days * 24 * 60 * 60,
        domain=settings.session_cookie_domain,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
        domain=settings.session_cookie_domain,
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _rate_limit(redis, key: str) -> None:
    rl = RedisTokenBucketRateLimiter(redis)
    res = await rl.allow(
        f"auth:{key}",
        limit=settings.auth_rate_limit_per_window,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if not res.allowed:
        raise AppError(42900, "操作过于频繁，请稍后再试", status_code=429)


def _safe_next(next_path: str) -> str:
    """Only allow same-site relative paths (block open redirect)."""
    return next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"


async def _serialize_current_user(db: AsyncSession, user: User) -> dict:
    identities = (
        await db.execute(select(AuthIdentity).where(AuthIdentity.user_id == user.id).order_by(AuthIdentity.created_at.asc()))
    ).scalars().all()
    return CurrentUserDTO(
        id=user.id,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        is_admin=user.is_admin,
        can_create=user.can_create,
        identities=[
            IdentitySummaryDTO(
                provider=identity.provider,
                email=identity.email,
                phone=identity.phone,
            )
            for identity in identities
        ],
    ).model_dump()


@router.post("/password/login")
async def password_login(
    req: PasswordLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service = _auth_service()
    web_session = await service.login_with_password(
        db,
        req.email,
        req.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    user = await db.get(User, web_session.user_id)
    _set_session_cookie(response, web_session.id)
    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}


@router.post("/register")
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await _rate_limit(redis, f"register:{_client_ip(request)}")
    await _auth_service().register_with_password(
        db, redis, email=req.email, password=req.password, nickname=req.nickname
    )
    return {
        "code": 0,
        "data": {"pending_verification": True, "email": normalize_email(req.email)},
        "message": "ok",
    }


@router.post("/verify-email")
async def verify_email(
    req: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    web_session = await _auth_service().verify_email(
        db,
        redis,
        req.token,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    user = await db.get(User, web_session.user_id)
    _set_session_cookie(response, web_session.id)
    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}


@router.post("/resend-verification")
async def resend_verification(
    req: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await _rate_limit(redis, f"resend:{normalize_email(req.email)}")
    await _auth_service().resend_verification(db, redis, req.email)
    return {"code": 0, "message": "ok"}


@router.post("/password/forgot")
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await _rate_limit(redis, f"forgot:{normalize_email(req.email)}")
    await _auth_service().request_password_reset(db, redis, req.email)
    return {"code": 0, "message": "ok"}  # 总是成功，防枚举


@router.post("/password/reset")
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await _auth_service().reset_password(db, redis, req.token, req.new_password)
    return {"code": 0, "message": "ok"}


@router.get("/oauth/{provider}/start")
async def oauth_start(provider: str, request: Request, next: str = "/"):
    if provider not in SUPPORTED_PROVIDERS:
        raise AppError(40004, "不支持的登录方式", status_code=404)
    request.session["oauth_next"] = _safe_next(next)
    client = oauth.create_client(provider)
    redirect_uri = f"{settings.public_api_url}/api/auth/oauth/{provider}/callback"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise AppError(40004, "不支持的登录方式", status_code=404)
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)  # validates state via session
    if provider == "google":
        userinfo = token.get("userinfo") or await client.userinfo(token=token)
    else:
        resp = await client.get("https://connect.linux.do/api/user", token=token)
        userinfo = resp.json()
    profile = normalize_profile(provider, dict(userinfo))
    user = await upsert_oauth_identity(db, provider, profile)
    web_session = _auth_service()._build_session(
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    db.add(web_session)
    await db.commit()
    next_path = _safe_next(request.session.pop("oauth_next", "/"))
    redirect = RedirectResponse(url=f"{settings.public_web_url}{next_path}", status_code=302)
    _set_session_cookie(redirect, web_session.id)
    return redirect


@router.get("/me")
async def current_user(
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    if user is None:
        return {"code": 0, "data": None, "message": "ok"}

    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}


_AVATAR_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_AVATAR_MAX_BYTES = 2 * 1024 * 1024
# data URL: data:image/png;base64,<payload>
_DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-z+]+);base64,(?P<b64>.+)$", re.DOTALL)


@router.patch("/me")
async def update_profile(
    req: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.nickname is not None:
        nickname = req.nickname.strip()
        if not 1 <= len(nickname) <= 50:
            raise AppError(42201, "昵称需为 1–50 个字符", status_code=422)
        user.nickname = nickname
    await db.commit()
    await db.refresh(user)
    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}


@router.post("/me/avatar")
async def upload_avatar(
    req: UploadAvatarRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 头像走 base64 data URL（JSON 提交），避免引入 multipart 依赖。
    match = _DATA_URL_RE.match(req.image.strip())
    if not match:
        raise AppError(42202, "图片格式不正确", status_code=422)
    ext = _AVATAR_TYPES.get(match.group("mime"))
    if not ext:
        raise AppError(42202, "仅支持 PNG / JPEG / WebP 图片", status_code=422)
    try:
        data = base64.b64decode(match.group("b64"), validate=True)
    except Exception:  # noqa: BLE001 — 任何解码失败都按非法图片处理
        raise AppError(42204, "图片数据无法解析", status_code=422)
    if not data:
        raise AppError(42204, "图片为空", status_code=422)
    if len(data) > _AVATAR_MAX_BYTES:
        raise AppError(42203, "头像不能超过 2MB", status_code=422)

    storage = get_image_storage()
    key = make_image_key("avatar", user.id, ext)
    user.avatar_url = await storage.save(data, key)
    await db.commit()
    await db.refresh(user)
    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}


@router.post("/password/change")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await _rate_limit(redis, f"pwchange:{user.id}")
    identity = (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.user_id == user.id,
                AuthIdentity.provider == "password",
            )
        )
    ).scalar_one_or_none()
    if not identity or not identity.credential_hash:
        raise AppError(40005, "当前账号未设置密码，无法修改", status_code=400)
    if not verify_password(req.old_password, identity.credential_hash):
        raise AppError(40103, "原密码错误", status_code=401)
    if verify_password(req.new_password, identity.credential_hash):
        raise AppError(42205, "新密码不能与原密码相同", status_code=422)
    identity.credential_hash = hash_password(req.new_password)
    await db.commit()
    return {"code": 0, "message": "ok"}


@router.post("/logout")
async def logout(
    response: Response,
    session_id: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    service = _auth_service()
    if user is not None and session_id:
        await service.logout(db, session_id)
    _clear_session_cookie(response)
    return {"code": 0, "message": "ok"}


@dev_router.post("/login")
async def dev_login(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service = _auth_service()
    web_session = await service.login_dev_user(
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    user = await db.get(User, web_session.user_id)
    _set_session_cookie(response, web_session.id)
    return {"code": 0, "data": await _serialize_current_user(db, user), "message": "ok"}
