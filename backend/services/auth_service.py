import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from middleware.error_handler import AppError
from models.user import AuthIdentity, User, WebSession
from services.auth_tokens import consume_token, create_token
from services.email_service import build_reset_email, build_verify_email, get_email_sender
from utils import utcnow

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_KEY_LEN = 64
PASSWORD_MIN_LEN = 8


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEY_LEN,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    key_b64 = base64.b64encode(derived_key).decode("ascii")
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt_b64}${key_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, n_value, r_value, p_value, salt_b64, key_b64 = password_hash.split("$")
    except ValueError:
        return False

    if algorithm != "scrypt":
        return False

    salt = base64.b64decode(salt_b64.encode("ascii"))
    expected_key = base64.b64decode(key_b64.encode("ascii"))
    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=int(n_value),
        r=int(r_value),
        p=int(p_value),
        dklen=len(expected_key),
    )
    return hmac.compare_digest(candidate, expected_key)


async def _find_password_identity(db: AsyncSession, email: str) -> AuthIdentity | None:
    return (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "password",
                AuthIdentity.provider_user_id == normalize_email(email),
            )
        )
    ).scalar_one_or_none()


class AuthService:
    async def login_with_password(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> WebSession:
        normalized_email = normalize_email(email)
        identity = (
            await db.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "password",
                    AuthIdentity.provider_user_id == normalized_email,
                )
            )
        ).scalar_one_or_none()
        if not identity or not identity.credential_hash or not verify_password(password, identity.credential_hash):
            raise AppError(40101, "邮箱或密码错误", status_code=401)

        if identity.verified_at is None:
            raise AppError(40302, "请先验证邮箱后再登录", status_code=403)

        user = await db.get(User, identity.user_id)
        if not user or user.status != "active":
            raise AppError(40102, "账号不可用", status_code=403)

        now = utcnow()
        user.last_login_at = now
        identity.last_login_at = now
        session = self._build_session(
            user_id=user.id,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def get_user_by_session_id(self, db: AsyncSession, session_id: str) -> User | None:
        web_session = await db.get(WebSession, session_id)
        if not web_session:
            return None
        if web_session.expires_at <= utcnow():
            await db.delete(web_session)
            await db.commit()
            return None

        now = utcnow()
        web_session.last_seen_at = now
        web_session.expires_at = now + timedelta(days=settings.web_session_days)
        user = await db.get(User, web_session.user_id)
        if not user or user.status != "active":
            await db.delete(web_session)
            await db.commit()
            return None
        await db.commit()
        return user

    async def logout(self, db: AsyncSession, session_id: str) -> None:
        web_session = await db.get(WebSession, session_id)
        if not web_session:
            return

        await db.delete(web_session)
        await db.commit()

    async def login_dev_user(
        self,
        db: AsyncSession,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> WebSession:
        if not settings.enable_dev_auth:
            raise AppError(40401, "开发登录未开启", status_code=404)

        identity = (
            await db.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "password",
                    AuthIdentity.provider_user_id == normalize_email(settings.dev_user_email),
                )
            )
        ).scalar_one_or_none()
        if not identity:
            raise AppError(50010, "开发账号未初始化", status_code=500)

        user = await db.get(User, identity.user_id)
        if not user or user.status != "active":
            raise AppError(50011, "开发账号不可用", status_code=500)

        now = utcnow()
        user.last_login_at = now
        identity.last_login_at = now
        session = self._build_session(
            user_id=user.id,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def register_with_password(
        self,
        db: AsyncSession,
        r,
        *,
        email: str,
        password: str,
        nickname: str | None = None,
    ) -> AuthIdentity:
        email_n = normalize_email(email)
        if len(password) < PASSWORD_MIN_LEN:
            raise AppError(40001, f"密码至少 {PASSWORD_MIN_LEN} 位", status_code=400)
        existing = await _find_password_identity(db, email_n)
        if existing and existing.verified_at is not None:
            raise AppError(40901, "该邮箱已注册，请登录或找回密码", status_code=409)
        if existing:  # 未验证 → 幂等再注册
            existing.credential_hash = hash_password(password)
            identity = existing
        else:
            user = User(status="active", nickname=nickname)
            db.add(user)
            await db.flush()
            identity = AuthIdentity(
                user_id=user.id,
                provider="password",
                provider_user_id=email_n,
                credential_hash=hash_password(password),
                email=email_n,
                verified_at=None,
            )
            db.add(identity)
            await db.flush()
        token = await create_token(r, "verify", {"identity_id": identity.id}, ttl=settings.email_verify_ttl_seconds)
        await db.commit()
        link = f"{settings.public_web_url}/verify-email?token={token}"
        subject, html, text = build_verify_email(link)
        await get_email_sender().send(to=email_n, subject=subject, html=html, text=text)
        return identity

    async def verify_email(
        self,
        db: AsyncSession,
        r,
        token: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> WebSession:
        payload = await consume_token(r, "verify", token)
        if not payload:
            raise AppError(40010, "验证链接无效或已过期", status_code=400)
        identity = await db.get(AuthIdentity, payload["identity_id"])
        if not identity:
            raise AppError(40010, "验证链接无效或已过期", status_code=400)
        if identity.verified_at is None:
            identity.verified_at = utcnow()
        user = await self.resolve_account_by_verified_email(db, identity.email, identity)
        now = utcnow()
        user.last_login_at = now
        identity.last_login_at = now
        session = self._build_session(user_id=user.id, user_agent=user_agent, ip_address=ip_address)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def resend_verification(self, db: AsyncSession, r, email: str) -> None:
        identity = await _find_password_identity(db, email)
        if not identity or identity.verified_at is not None:
            return  # 不泄漏邮箱是否存在 / 是否已验证
        token = await create_token(r, "verify", {"identity_id": identity.id}, ttl=settings.email_verify_ttl_seconds)
        link = f"{settings.public_web_url}/verify-email?token={token}"
        subject, html, text = build_verify_email(link)
        await get_email_sender().send(to=identity.email, subject=subject, html=html, text=text)

    async def request_password_reset(self, db: AsyncSession, r, email: str) -> None:
        identity = await _find_password_identity(db, email)
        if not identity or identity.verified_at is None:
            return  # 防枚举：对不存在/未验证邮箱静默
        token = await create_token(r, "reset", {"identity_id": identity.id}, ttl=settings.password_reset_ttl_seconds)
        link = f"{settings.public_web_url}/reset-password?token={token}"
        subject, html, text = build_reset_email(link)
        await get_email_sender().send(to=identity.email, subject=subject, html=html, text=text)

    async def reset_password(self, db: AsyncSession, r, token: str, new_password: str) -> None:
        if len(new_password) < PASSWORD_MIN_LEN:
            raise AppError(40001, f"密码至少 {PASSWORD_MIN_LEN} 位", status_code=400)
        payload = await consume_token(r, "reset", token)
        if not payload:
            raise AppError(40010, "重置链接无效或已过期", status_code=400)
        identity = await db.get(AuthIdentity, payload["identity_id"])
        if not identity:
            raise AppError(40010, "重置链接无效或已过期", status_code=400)
        identity.credential_hash = hash_password(new_password)
        # 重置后失效该用户全部 session，强制重新登录
        await db.execute(delete(WebSession).where(WebSession.user_id == identity.user_id))
        await db.commit()

    async def resolve_account_by_verified_email(
        self,
        db: AsyncSession,
        email: str | None,
        identity: AuthIdentity,
    ) -> User:
        """不变式：一个已验证邮箱只对应一个 user。

        当 `identity` 刚变为已验证时调用：若该邮箱已属另一个 user 的已验证身份，
        把 `identity` 合并过去并清理可能留下的孤儿空 user。
        """
        if not email:
            return await db.get(User, identity.user_id)
        email_n = normalize_email(email)
        other = (
            await db.execute(
                select(AuthIdentity)
                .where(
                    AuthIdentity.email == email_n,
                    AuthIdentity.verified_at.is_not(None),
                    AuthIdentity.id != identity.id,
                )
                .order_by(AuthIdentity.created_at.asc())
            )
        ).scalars().first()
        if other is None:
            return await db.get(User, identity.user_id)
        orphan_user_id = identity.user_id
        identity.user_id = other.user_id
        await db.flush()
        if orphan_user_id != other.user_id:
            remaining = (
                await db.execute(select(AuthIdentity).where(AuthIdentity.user_id == orphan_user_id))
            ).scalars().first()
            if remaining is None:
                orphan = await db.get(User, orphan_user_id)
                if orphan:
                    await db.delete(orphan)
        return await db.get(User, other.user_id)

    def _build_session(
        self,
        user_id: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> WebSession:
        return WebSession(
            user_id=user_id,
            expires_at=utcnow() + timedelta(days=settings.web_session_days),
            user_agent=user_agent,
            ip_address=ip_address,
        )
