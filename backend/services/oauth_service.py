"""OAuth (Google / LinuxDo) via authlib.

`oauth` holds the registered clients (token exchange / OIDC handled by authlib).
`upsert_oauth_identity` turns a normalized provider profile into a logged-in user,
reusing the same verified-email merge invariant as email verification.
"""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import AuthIdentity, User
from services.auth_service import AuthService
from utils import utcnow

SUPPORTED_PROVIDERS = ("google", "linuxdo")

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name="linuxdo",
    client_id=settings.linuxdo_client_id,
    client_secret=settings.linuxdo_client_secret,
    authorize_url="https://connect.linux.do/oauth2/authorize",
    access_token_url="https://connect.linux.do/oauth2/token",
    userinfo_endpoint="https://connect.linux.do/api/user",
    client_kwargs={"scope": "read"},
)


def _norm_email(value: str | None) -> str | None:
    return (value or "").strip().lower() or None


def normalize_profile(provider: str, info: dict) -> dict:
    """Map each provider's userinfo to {provider_user_id, email, email_verified, name, avatar}."""
    if provider == "google":
        return {
            "provider_user_id": str(info["sub"]),
            "email": _norm_email(info.get("email")),
            "email_verified": bool(info.get("email_verified")),
            "name": info.get("name"),
            "avatar": info.get("picture"),
        }
    # linuxdo (Discourse Connect) — only treat email as verified if the provider says so
    return {
        "provider_user_id": str(info["id"]),
        "email": _norm_email(info.get("email")),
        "email_verified": bool(info.get("email_verified", info.get("active", False))),
        "name": info.get("name") or info.get("username"),
        "avatar": info.get("avatar_url"),
    }


async def upsert_oauth_identity(db: AsyncSession, provider: str, profile: dict) -> User:
    svc = AuthService()
    existing = (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_user_id == profile["provider_user_id"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        user = await db.get(User, existing.user_id)
        user.last_login_at = utcnow()
        await db.commit()
        return user

    verified = profile["email_verified"]
    user = User(status="active", nickname=profile.get("name"), avatar_url=profile.get("avatar"))
    db.add(user)
    await db.flush()
    identity = AuthIdentity(
        user_id=user.id,
        provider=provider,
        provider_user_id=profile["provider_user_id"],
        email=profile.get("email"),
        verified_at=utcnow() if verified else None,
        profile=profile,
    )
    db.add(identity)
    await db.flush()
    if verified and profile.get("email"):
        user = await svc.resolve_account_by_verified_email(db, profile["email"], identity)
    user.last_login_at = utcnow()
    await db.commit()
    return user
