"""Bots — storage layer.

One physical table backs two API shapes: `BotService` (the rich admin
registry — FK model refs, persona/system prompt) and
`AdminOpsService.simple_bots` (free-text model name, a lighter status
vocabulary). A bot created via either surface is visible to both; fields
only one surface uses stay nullable.
"""

from typing import Optional

from sqlalchemy import ARRAY, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Union of BotFull's status ("active", "draft", "inactive") and the
# simple Bot's ("active", "paused", "draft").
_STATUSES = ("active", "draft", "inactive", "paused")
_TYPES = ("interviewer", "reviewer", "co-pilot")  # simple Bot.type only


class Bot(Base, TimestampMixin):
    __tablename__ = "bots"
    __table_args__ = (Index("ix_bots_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_STATUSES, name="bot_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="draft",
    )
    sessions_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Rich view (BotFull, /api/admin/bots) ──────────────────────────────
    # full_name/avatar/color are nullable here (a simple-created bot has
    # none of them) — BotService derives sensible fallbacks at read time
    # so BotFull's required fields are always satisfiable regardless of
    # which surface created the row. See bot_service.py.
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    avatar: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    specializations: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    primary_model_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fallback_model_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    persona: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avg_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ── Simple view (Bot, /api/bots) ───────────────────────────────────────
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bot_type: Mapped[Optional[str]] = mapped_column(
        Enum(*_TYPES, name="bot_type", native_enum=False, create_constraint=True), nullable=True
    )
    avg_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Free-text model name for bots created without a real ai_models FK
    # (the simple creation flow never references ai_models at all).
    model_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
