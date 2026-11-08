"""Alembic environment — async, targets Supabase Postgres directly.

Runs DDL over `Settings.DATABASE_MIGRATION_URL` (the direct, port-5432
connection), never the pooled `DATABASE_URL` — transaction-mode pooling
can split a multi-statement migration across different backend
connections mid-flight, which would corrupt it.
"""

import asyncio
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import the full model package so every model's table registers on
# `Base.metadata` before autogenerate inspects it. See app/models/__init__.py.
import app.models  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_url() -> str:
    settings = get_settings()
    if not settings.DATABASE_MIGRATION_URL:
        raise RuntimeError(
            "DATABASE_MIGRATION_URL is not configured — set it to the Supabase "
            "direct (non-pooled, port 5432) connection string. See .env.example."
        )
    return settings.DATABASE_MIGRATION_URL


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (`alembic upgrade --sql`)."""
    context.configure(
        url=_migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live, direct (non-pooled) connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _migration_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"prepare_threshold": None},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Programmatic callers (e.g. the test suite running `alembic upgrade`
    # against TEST_DATABASE_URL) may hand us an already-open sync
    # connection via `config.attributes["connection"]`; when present we
    # must use it instead of building our own engine from settings, and
    # run synchronously — no event loop required. See tests/conftest.py.
    _external_connection = config.attributes.get("connection")
    if _external_connection is not None:
        _do_run_migrations(_external_connection)
    else:
        if sys.platform == "win32":
            # psycopg's async mode can't run on the default Proactor loop.
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_migrations_online())
