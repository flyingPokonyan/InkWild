from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import async_session  # noqa: E402
from models.user import AuthIdentity, User  # noqa: E402
from services.auth_service import hash_password, normalize_email  # noqa: E402
from utils import utcnow  # noqa: E402

from sqlalchemy import select  # noqa: E402


async def create_or_promote_admin(email: str, password: str | None) -> User:
    normalized_email = normalize_email(email)
    async with async_session() as db:
        identity = (
            await db.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "password",
                    AuthIdentity.provider_user_id == normalized_email,
                )
            )
        ).scalar_one_or_none()

        if identity:
            user = await db.get(User, identity.user_id)
            if not user:
                raise RuntimeError("Password identity exists but its user is missing")
            user.is_admin = True
            if identity.verified_at is None:
                identity.verified_at = utcnow()
            await db.commit()
            await db.refresh(user)
            return user

        if not password:
            password = getpass.getpass("Password: ")
        if not password:
            raise RuntimeError("Password is required when creating a new admin user")

        user = User(nickname=normalized_email.split("@", 1)[0], is_admin=True)
        db.add(user)
        await db.flush()
        db.add(
            AuthIdentity(
                user_id=user.id,
                provider="password",
                provider_user_id=normalized_email,
                credential_hash=hash_password(password),
                email=normalized_email,
                verified_at=utcnow(),
            )
        )
        await db.commit()
        await db.refresh(user)
        return user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or promote an admin password user.")
    parser.add_argument("email", help="Admin email address")
    parser.add_argument("--password", help="Password for a new password identity")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user = asyncio.run(create_or_promote_admin(args.email, args.password))
    print(f"admin user ready: {user.id} {normalize_email(args.email)}")


if __name__ == "__main__":
    main()
