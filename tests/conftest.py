"""Shared pytest fixtures.

`client` (and its alias `pg_client`) runs the full app against a real
local Postgres — see the "Postgres fixtures" section below — inside a
transaction that's rolled back per test.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Force DEBUG before app imports so dev-token auth is enabled.
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

# psycopg's async mode cannot run on Windows' default ProactorEventLoop;
# the Selector loop is required for the asyncpg/psycopg event-loop contract.
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def client(pg_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """ASGI test client, backed by the real (transaction-rolled-back)
    Postgres session below.

    httpx's ASGITransport does NOT run the FastAPI lifespan, so the seeds
    that normally run at startup are invoked explicitly here.
    """
    from app.db.seed import run_seeds
    from app.db.session import get_session
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_session] = lambda: pg_session
    await run_seeds(pg_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Helpers ───────────────────────────────────────────────────────────────


def admin_token() -> str:
    """Mirror the frontend's dev-token format: `dev_<base64(json)>`."""
    import base64
    import json

    payload = json.dumps({"email": "admin@anveksha.dev", "role": "admin"})
    return "dev_" + base64.b64encode(payload.encode()).decode()


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token()}"}


# ── Postgres fixtures ────────────────────────────────────────────────────
#
# Tests run against a real local Postgres (docker-compose --profile test
# up postgres-test), not a fake. The schema is built by running the real
# Alembic migration chain to head — the same path a fresh dev/production
# database takes — so model↔migration drift fails here instead of at
# deploy time (see tests/test_migrations.py). Each test gets one
# connection + outer transaction, rolled back at teardown; the session
# joins it via a SAVEPOINT so an in-test `session.commit()` only releases
# the savepoint, never the outer transaction — a committed write from a
# DIFFERENT session (e.g. a self-contained `get_sessionmaker()` session)
# still persists and is NOT covered by this rollback, so clean those up
# explicitly. The engine is session-scoped and migrations run once.


@pytest.fixture(scope="session")
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.TEST_DATABASE_URL, echo=False)

    base_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(base_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(base_dir / "app" / "db" / "migrations"))

    def _upgrade(sync_conn) -> None:
        # Passing the open connection via config.attributes makes env.py
        # run the chain on it instead of building its own engine from
        # DATABASE_MIGRATION_URL (which may point elsewhere in dev).
        cfg.attributes["connection"] = sync_conn
        command.upgrade(cfg, "head")

    async with engine.begin() as conn:
        await conn.run_sync(_upgrade)
    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with pg_engine.connect() as connection:
        trans = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
async def pg_client(client: AsyncClient) -> AsyncClient:
    """Alias for `client`, kept for tests that want to be explicit about
    exercising Postgres-backed entities; functionally identical to
    `client` (every entity is Postgres-backed now)."""
    return client
