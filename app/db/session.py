"""Async engine/session lifecycle for Supabase Postgres.

A small `AsyncAdaptedQueuePool` per app instance — connections are reused
across requests within one process rather than re-handshaked every time,
while Supabase's Supavisor pooler (transaction mode) still does the real
multiplexing onto Postgres backends one layer down, so any number of app
instances still share the project's connection budget (`pool_size` here
times instance count, not per-request). Driver is `psycopg` v3 with
`prepare_threshold=None` (disables server-side prepared statements, which
transaction-mode pooling doesn't support across reused connections).
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core.config import get_settings

log = logging.getLogger(__name__)


class _EngineState:
    engine: Optional[AsyncEngine] = None
    sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


_state = _EngineState()


async def connect_to_db() -> None:
    """Create the engine + session factory. Idempotent; connects lazily."""
    if _state.engine is not None:
        return

    settings = get_settings()
    if not settings.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured — set it to the Supabase pooled "
            "(Supavisor transaction mode, port 6543) connection string. "
            "See .env.example."
        )
    log.info(
        "Configuring Supabase Postgres engine (pool_size=%d, max_overflow=%d).",
        settings.DATABASE_POOL_SIZE,
        settings.DATABASE_MAX_OVERFLOW,
    )

    _state.engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE_S,
        pool_pre_ping=True,
        echo=settings.DATABASE_ECHO,
        connect_args={"prepare_threshold": None},
    )
    _state.sessionmaker = async_sessionmaker(_state.engine, expire_on_commit=False)


async def close_db() -> None:
    if _state.engine is not None:
        await _state.engine.dispose()
        log.info("Database engine disposed.")
    _state.engine = None
    _state.sessionmaker = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the active session factory, for callers outside a request (e.g. seeds)."""
    if _state.sessionmaker is None:
        raise RuntimeError("Database not initialised — call connect_to_db() first.")
    return _state.sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — one `AsyncSession` per request, committed on
    success and rolled back on exception. Keep handlers fast: the pooled
    connection stays checked out for the whole request."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
        await session.commit()


@asynccontextmanager
async def session_scope(db: Optional[AsyncSession] = None, *, write: bool = False) -> AsyncIterator[AsyncSession]:
    """The caller's session when it has one (e.g. a request), otherwise a
    short-lived one (e.g. a Temporal activity with no request cycle).

    With `write=True` the block's changes are flushed into the caller's
    transaction (the caller commits), or committed in the short-lived
    session. Nothing is flushed or committed if the block raises.
    """
    if db is not None:
        yield db
        if write:
            await db.flush()
        return
    async with get_sessionmaker()() as session:
        yield session
        if write:
            await session.commit()
