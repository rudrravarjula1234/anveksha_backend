"""AI model configuration — storage layer. Mirrors `app/schemas/ai_model.py`'s
`AdminModel` API contract with snake_case columns; `AIModelService` maps
between the two.
"""

from typing import Optional

from sqlalchemy import Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Kept in sync with app.schemas.ai_model.ModelProvider / ModelStatus.
# `native_enum=False` renders as VARCHAR rather than a Postgres ENUM TYPE
# (no ALTER TYPE friction if the provider list grows) — but SQLAlchemy's
# `create_constraint` defaults to False even then, so it must be passed
# explicitly or you silently get an unconstrained VARCHAR with no DB-level
# validation at all. Every Enum column in this migration must set it.
_PROVIDERS = ("Anthropic", "OpenAI", "Azure OpenAI", "Google Vertex", "AWS Bedrock", "Custom")
_STATUSES = ("active", "inactive")


class AIModel(Base, TimestampMixin):
    __tablename__ = "ai_models"
    __table_args__ = (Index("ix_ai_models_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(
        Enum(*_PROVIDERS, name="ai_model_provider", native_enum=False, create_constraint=True),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Provider-side model identifier — frequently filtered on (was a
    # secondary Mongo index in the legacy store; carried over as a plain
    # Postgres index here).
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    status: Mapped[str] = mapped_column(
        Enum(*_STATUSES, name="ai_model_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="active",
        index=True,
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Numeric, not Float — real per-token dollar costs; asdecimal=False keeps
    # the Python-side value a plain float (unchanged call-site contract)
    # while storing it as exact fixed-point in Postgres, not IEEE754.
    cost_per_1k_in: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0.0)
    cost_per_1k_out: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0.0)
    # Self-referential FK — unenforced in Mongo ("we don't enforce
    # referential integrity at the database layer" per the old repo's
    # docstring); enforced for real now.
    fallback_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
