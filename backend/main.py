import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from api.admin import router as admin_router
from api.admin_announcements import router as admin_announcements_router
from api.admin_analytics import router as admin_analytics_router
from api.admin_credits import router as admin_credits_router
from api.admin_audit import router as admin_audit_router
from api.admin_dashboard import router as admin_dashboard_router
from api.admin_models import router as admin_models_router
from api.admin_content import router as admin_content_router
from api.admin_review import router as admin_review_router
from api.admin_users import router as admin_users_router
from api.auth import dev_router as dev_auth_router
from api.auth import router as auth_router
from api.credits import router as credits_router
from api.game import router as game_router
from api.notifications import router as notifications_router
from api.workshop import router as workshop_router
from api.worlds import router as worlds_router
from config import settings
from database import async_session
from middleware.error_handler import ErrorHandlerMiddleware
from middleware.logging import LoggingMiddleware
from sentry_config import init_sentry
from services.model_management import ensure_default_model_management_state

logger = logging.getLogger(__name__)
init_sentry()


# How often the credit-hold sweep recovers orphaned reservations + failed
# settlements (design §5.4). Lightweight; reuses the running event loop.
_CREDIT_SWEEP_INTERVAL_SECONDS = 300


async def _credit_sweep_loop() -> None:
    from services import credit_service

    while True:
        try:
            await asyncio.sleep(_CREDIT_SWEEP_INTERVAL_SECONDS)
            async with async_session() as session:
                await credit_service.sweep_holds(session)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001 — the sweep must never crash the app
            logger.warning("credit_sweep_failed", exc_info=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        async with async_session() as session:
            await ensure_default_model_management_state(session)
    except Exception:  # noqa: BLE001
        logger.warning("model_management_bootstrap_failed", exc_info=True)
    sweep_task = asyncio.create_task(_credit_sweep_loop())
    try:
        yield
    finally:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="InkWild", version="0.1.0", lifespan=lifespan)

app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(LoggingMiddleware)
_default_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",  # admin-frontend dev
    "http://127.0.0.1:3001",
    "https://inkwild.vercel.app",
]
_extra_cors = [o.strip() for o in settings.cors_extra_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_cors_origins + _extra_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Short-lived signed-cookie session, used only to carry OAuth state/nonce across
# the provider redirect (authlib's blessed flow). Separate from the auth cookie.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    same_site="lax",
    https_only=not settings.debug,
)
app.include_router(admin_router)
app.include_router(admin_announcements_router)
app.include_router(admin_analytics_router)
app.include_router(admin_credits_router)
app.include_router(admin_audit_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_models_router)
app.include_router(admin_content_router)
app.include_router(admin_review_router)
app.include_router(admin_users_router)
app.include_router(auth_router)
app.include_router(dev_auth_router)
app.include_router(credits_router)
app.include_router(game_router)
app.include_router(notifications_router)
app.include_router(workshop_router)
app.include_router(worlds_router)


async def check_database() -> str:
    async with async_session() as session:
        await session.execute(text("SELECT 1"))
    return "ok"


async def check_redis() -> str:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
    finally:
        await client.aclose()
    return "ok"


@app.get("/health")
async def health() -> dict[str, object]:
    components: dict[str, str] = {}

    for name, check in (("database", check_database), ("redis", check_redis)):
        try:
            components[name] = await check()
        except Exception:  # noqa: BLE001
            components[name] = "error"

    if any(status != "ok" for status in components.values()):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "components": components,
            },
        )

    return {"status": "ok", "components": components}


# Static file serving for locally stored images
_static_dir = Path("static/images")
_static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=str(_static_dir)), name="images")
