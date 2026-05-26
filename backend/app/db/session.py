"""
Database engine + session factory.

Two contexts use these:
1. FastAPI request handlers - long-lived event loop, benefits from a pool.
2. Celery workers - each task spins up a fresh asyncio loop via
   asyncio.new_event_loop(), which is incompatible with a connection pool
   whose internal Futures are bound to the original loop. The symptom is
   'Future attached to a different loop' on db.execute().

Solution: detect which context we're in by checking sys.argv. Celery workers
launch with 'celery' in the command; the API uses 'uvicorn'. The Celery
path uses NullPool (one fresh connection per call); the API path uses a
proper pool.
"""

import sys
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.core.config import get_settings

settings = get_settings()


def _is_celery_worker() -> bool:
    # When celery launches, sys.argv[0] ends with 'celery' and 'worker' is in argv.
    argv0 = (sys.argv[0] if sys.argv else "").lower()
    return "celery" in argv0 or "worker" in sys.argv


_engine_kwargs: dict = {
    "echo": settings.app_env == "development",
}

if _is_celery_worker():
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    })

engine = create_async_engine(settings.database_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
