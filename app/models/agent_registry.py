"""Agent registry — storage layer.

A fixed 6-row config table (Anveksha ships a fixed set of pre-defined
agents; admins can only re-point them at a different model / edit their
system message, never add or remove rows).
"""

from typing import Optional

from sqlalchemy import ARRAY, Boolean, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Kept in sync with app.schemas.agent_registry.AgentId.
_AGENT_IDS = (
    "interviewer_brief",
    "report_generator",
    "gap_analyzer",
    "gray_analyzer",
    "candidate_search",
    "candidate_chat",
)


class AgentConfig(Base, TimestampMixin):
    __tablename__ = "agent_registry"

    id: Mapped[str] = mapped_column(
        Enum(*_AGENT_IDS, name="agent_registry_id", native_enum=False, create_constraint=True),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    used_by: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    model_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True, index=True
    )
    system_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The shipped default, kept alongside so admins can reset.
    default_system_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.4)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
