"""Application configuration loaded from environment variables / `.env`.

All settings are read once at startup via `get_settings()` (cached). Add
new options here as Pydantic fields so we get validation + defaults +
documentation in one place.
"""

from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, computed_field
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

    # ─── Mongo ───────────────────────────────────────────────────────────
    # Each field accepts both the historical MONGO_* env name and the
    # deployment's MONGODB_* schema (MONGODB_URI / MONGODB_USERNAME /
    # MONGODB_PASSWORD / MONGODB_DB_NAME). A full URI (cloud Atlas srv string)
    # takes precedence over the component parts.
    MONGO_URI: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("MONGO_URI", "MONGODB_URI"),
        description="Full URI overrides component parts.",
    )
    MONGO_USERNAME: str = Field(
        default="anveksha",
        validation_alias=AliasChoices("MONGO_USERNAME", "MONGODB_USERNAME"),
    )
    MONGO_PASSWORD: str = Field(
        default="changeme",
        validation_alias=AliasChoices("MONGO_PASSWORD", "MONGODB_PASSWORD"),
    )
    MONGO_DATABASE: str = Field(
        default="anveksha",
        validation_alias=AliasChoices("MONGO_DATABASE", "MONGODB_DB_NAME", "MONGODB_DATABASE"),
    )
    MONGO_HOST: str = Field(default="mongo")
    MONGO_PORT: int = Field(default=27017)
    MONGO_AUTH_SOURCE: str = Field(default="admin")

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
    def mongo_connection_uri(self) -> str:
        """Resolve the Mongo URI we'll actually connect with.

        Precedence: explicit MONGO_URI > component-built URI.
        Component path URL-encodes credentials so passwords with `@`, `:`,
        `/`, `?`, `#` etc. don't corrupt the connection string.
        """
        if self.MONGO_URI:
            return self.MONGO_URI
        user = quote_plus(self.MONGO_USERNAME)
        pw = quote_plus(self.MONGO_PASSWORD)
        return (
            f"mongodb://{user}:{pw}@{self.MONGO_HOST}:{self.MONGO_PORT}/"
            f"{self.MONGO_DATABASE}?authSource={self.MONGO_AUTH_SOURCE}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor — cached to keep one Settings instance app-wide."""
    return Settings()
