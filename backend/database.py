from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


def _engine_options() -> dict[str, object]:
    options: dict[str, object] = {"echo": settings.debug}
    if not settings.database_url.startswith("sqlite"):
        options.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout,
                # pre_ping: validate pooled connections with a lightweight
                # `SELECT 1` before handing them to the caller. Without this,
                # connections that the server closed (idle timeout / cloud DB
                # cycling / dev docker restart) come back to the app as
                # "connection is closed" InterfaceError on first use — the
                # exact failure we saw under concurrent / restart load on
                # 2026-05-27. SQLAlchemy then transparently reconnects on
                # ping failure. Negligible perf cost; pure stability win.
                "pool_pre_ping": True,
                # Also recycle after 30 min so we proactively avoid hitting
                # server-side idle timeouts (default Postgres 8h, cloud DBs
                # often shorter).
                "pool_recycle": 1800,
            }
        )
    return options


engine = create_async_engine(settings.database_url, **_engine_options())
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session
