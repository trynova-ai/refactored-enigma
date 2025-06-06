"""
Small helper that:

1. Builds an async SQLAlchemy engine that still uses asyncpg under the hood.
2. Exposes `Base` for models.
3. Runs `metadata.create_all()` at application start-up so tables appear
   automatically if they’re missing.
"""

import os
from functools import lru_cache
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy import text

from config import get_settings

settings = get_settings()

# --------------------------------------------------------------------------- #
# Engine / Session factory
# --------------------------------------------------------------------------- #

DB_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(DB_URL, echo=False, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()


@asynccontextmanager
async def get_session() -> AsyncSession:
    """
    Usage:
        async with get_session() as db:
            await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        yield session


# --------------------------------------------------------------------------- #
# One-shot auto-migration
# --------------------------------------------------------------------------- #

async def create_schema() -> None:
    """
    Auto-creates *all* tables defined on `Base`.  No-op if they already exist.
    Called once by FastAPI's lifespan event (see gateway/app.py).
    """
    async with engine.begin() as conn:
        # Optionally set search_path etc. here:
        # await conn.execute(text('SET search_path TO public'))
        await conn.run_sync(Base.metadata.create_all)
