"""Application configuration loaded from environment variables / `.env`.

All settings are read once at startup via `get_settings()` (cached). Add
new options here as Pydantic fields so we get validation + defaults +
documentation in one place.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed environment configuration.

    Read from process env, optionally seeded by `.env` in the project root.
    Field names match the env keys verbatim (case-insensitive).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # tolerate env keys we don't model yet
    )

    # ─── Runtime ─────────────────────────────────────────────────────────
    DEBUG: bool = Field(default=False, description="Enables dev-token auth + verbose errors.")
    LOG_LEVEL: str = Field(default="info")
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    PROJECT_NAME: str = Field(default="Anveksha")
    VERSION: str = Field(default="0.1.0")

    # ─── Database (Supabase Postgres) ───────────────────────────────────────
    # DATABASE_URL: pooled (Supavisor transaction mode, port 6543) — runtime traffic.
    # DATABASE_MIGRATION_URL: direct (port 5432) — Alembic DDL only.
    # Optional so the app/test-suite can boot unconfigured; connect_to_db()
    # fails loudly on first query if DATABASE_URL is unset.
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Pooled Supavisor (transaction mode, port 6543) connection URL.",
    )
    DATABASE_MIGRATION_URL: Optional[str] = Field(
        default=None,
        description="Direct (port 5432) connection URL, used only by Alembic.",
    )
    DATABASE_ECHO: bool = Field(
        default=False, description="Log every SQL statement (SQLAlchemy `echo=`). Dev only."
    )
    TEST_DATABASE_URL: str = Field(
        default="postgresql+psycopg://anveksha_test:anveksha_test@localhost:55432/anveksha_test",
        description="Local Postgres used by the test suite, never the real Supabase project.",
    )
    # Per-instance connection pool against Supavisor. Kept small and
    # multiplied by however many app instances run — the shared budget is
    # Supavisor's, not a single process's. See app/db/session.py.
    DATABASE_POOL_SIZE: int = Field(default=10, description="Persistent connections held per app instance.")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, description="Extra connections allowed above pool_size under burst load.")
    DATABASE_POOL_RECYCLE_S: int = Field(
        default=1800, description="Recycle pooled connections after this many seconds (avoids stale/killed ones)."
    )

    # ─── CORS ────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = Field(default="http://localhost:5173")

    # ─── JWT (forward-looking; dev tokens cover today) ───────────────────
    JWT_SECRET: str = Field(default="replace-me")
    JWT_ALG: str = Field(default="HS256")
    JWT_ACCESS_TTL_MIN: int = Field(default=60)
    JWT_REFRESH_TTL_DAYS: int = Field(default=14)

    # ─── Temporal (durable agent workflows) ──────────────────────────────
    # Optional. The app boots and serves inline agents without Temporal;
    # the /api/workflows/* endpoints return 503 until a Temporal server is
    # reachable AND the `temporalio` extra is installed. The worker runs as
    # a separate process (docker service `temporal-worker`).
    TEMPORAL_HOST: str = Field(default="localhost:7233")
    TEMPORAL_NAMESPACE: str = Field(default="default")
    TEMPORAL_TASK_QUEUE: str = Field(default="anveksha-agents")

    # ─── Google OAuth ────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: Optional[str] = Field(
        default=None,
        description=(
            "OAuth client id — MUST match the frontend's VITE_GOOGLE_CLIENT_ID. "
            "When set, /api/auth/google-register verifies real Google ID tokens "
            "(audience check against this id). When unset and DEBUG=true, the "
            "endpoint falls back to the dev stub."
        ),
    )

    # ─── Agents (app/agents) ─────────────────────────────────────────────
    CREDENTIAL_ENCRYPTION_KEY: Optional[str] = Field(
        default=None,
        description=(
            "Fernet key for encrypting provider API keys at rest "
            "(model_credentials collection). Generate with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())". '
            "When unset and DEBUG=true, a stable dev key is derived from JWT_SECRET."
        ),
    )

    # ── Derived values ────────────────────────────────────────────────────

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor — cached to keep one Settings instance app-wide."""
    return Settings()
