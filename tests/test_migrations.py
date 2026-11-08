"""Schema-versioning tests — enforce the two invariants `create_all` could not:

1. A brand-new database can be initialized from the Alembic migration
   history alone (fresh scratch DB → `alembic upgrade head`).
2. The SQLAlchemy models and the migration chain never drift: any model
   change without a matching migration fails `alembic check` here instead
   of breaking `alembic upgrade head` in a deploy.

Both run against the real local test Postgres (see tests/conftest.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

SCRATCH_DB = "anveksha_migrationscratch"

# Core tables that must exist after a from-scratch upgrade; a tripwire
# against a migration chain that silently builds an empty schema.
EXPECTED_TABLES = ("users", "user_roles", "ai_models", "bots", "workflow_runs", "skill_ledgers")


def _alembic_config() -> Config:
    base_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(base_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(base_dir / "app" / "db" / "migrations"))
    return cfg


async def test_models_match_migrations_no_drift(pg_engine: AsyncEngine) -> None:
    """`alembic check` against the (already migrated) test DB: fails if the
    models describe anything the migration chain doesn't produce, or vice
    versa — the CI enforcement point for model↔migration parity."""
    cfg = _alembic_config()

    async with pg_engine.connect() as conn:

        def _check(sync_conn) -> None:
            cfg.attributes["connection"] = sync_conn
            command.check(cfg)
        await conn.run_sync(_check)


async def test_fresh_database_initializes_from_migrations() -> None:
    """Build an empty scratch database from the migration chain alone,
    verify the head revision and core tables, then drop it."""
    from app.core.config import get_settings

    scratch_url = make_url(get_settings().TEST_DATABASE_URL).set(database=SCRATCH_DB)
    # Superuser-style admin connection to the server, not a database, so
    # CREATE/DROP DATABASE can run outside any transaction.
    admin_url = scratch_url.set(database="postgres")

    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        try:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
                await conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
        except Exception as exc:  # pragma: no cover - env without CREATEDB
            pytest.skip(f"cannot create scratch database on test server: {exc}")

        cfg = _alembic_config()
        head = ScriptDirectory.from_config(cfg).get_current_head()

        scratch_engine = create_async_engine(scratch_url)
        try:
            async with scratch_engine.begin() as conn:

                def _upgrade(sync_conn) -> None:
                    cfg.attributes["connection"] = sync_conn
                    command.upgrade(cfg, "head")

                await conn.run_sync(_upgrade)

            async with scratch_engine.connect() as conn:
                version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
                assert version == head, f"alembic_version {version!r} != chain head {head!r}"

                rows = await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
                present = {r[0] for r in rows}
                missing = [t for t in EXPECTED_TABLES if t not in present]
                assert not missing, f"fresh upgrade produced no tables: {missing}"
        finally:
            await scratch_engine.dispose()
    finally:
        try:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        finally:
            await admin_engine.dispose()
