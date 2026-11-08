"""Token usage records — storage layer.

`agent_ids` is a child table (`token_usage_agent_ids`), not an `ARRAY`
column — it's queried by value (`get_usage_by_agent(agent_id)`), unlike
purely-display string lists elsewhere.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Kept in sync with app.agents.service's orchestration branches.
_ORCHESTRATION_TYPES = ("direct", "group_chat", "round_robin", "workflow", "hierarchical")


class TokenUsage(Base):
    __tablename__ = "token_usage"
    __table_args__ = (
        # Matches `get_usage_by_model`'s (model_name, date-range) query
        # shape from the migration plan's standards checklist.
        Index("ix_token_usage_model_name_created_at", "model_name", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    orchestration_type: Mapped[str] = mapped_column(
        Enum(*_ORCHESTRATION_TYPES, name="token_usage_orchestration_type", native_enum=False, create_constraint=True),
        nullable=False,
    )

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)

    # Numeric, not Float — real dollar costs; asdecimal=False keeps the
    # Python-side value a plain float while storing exact fixed-point.
    input_cost: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0.0)
    output_cost: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0.0)
    total_cost: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    interview_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    agent_ids: Mapped[list["TokenUsageAgentId"]] = relationship(
        back_populates="usage", cascade="all, delete-orphan", lazy="selectin", order_by="TokenUsageAgentId.id"
    )


class TokenUsageAgentId(Base):
    __tablename__ = "token_usage_agent_ids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_usage_id: Mapped[str] = mapped_column(
        ForeignKey("token_usage.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    usage: Mapped["TokenUsage"] = relationship(back_populates="agent_ids")


class TokenUsageModelTotals(Base):
    """Running per-model totals of `token_usage`, maintained by the
    statement-level `trg_token_usage_totals_{ins,upd,del,trunc}` triggers
    (migration 0001) — never written by the app. Platform metrics
    read these few rows instead of aggregating the whole append-only ledger."""

    __tablename__ = "token_usage_model_totals"

    model_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    requests: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_cost: Mapped[float] = mapped_column(Numeric(18, 6, asdecimal=False), nullable=False, default=0.0)
