"""Skill ledger — storage layer. One row per candidate (`candidate_id`
is the primary key). `InterviewerStatus`'s scalar fields are flattened
directly onto `skill_ledgers` (a true 1:1 relationship); `skills`,
`authorities`, and `externalProof` get their own child tables.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Kept in sync with app.schemas.skill.*
_SKILL_STATES = ("verified", "partial", "gray", "claimed")
_INTERVIEWER_MODES = ("none", "pending", "freelance", "specialist")
_INTERVIEWER_ORIGINS = ("bot-discovered", "self-requested", "admin-invited")


class SkillLedger(Base, TimestampMixin):
    __tablename__ = "skill_ledgers"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    candidate_location: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    candidate_initials: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    dossier_id: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gray_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Editable profile fields (PATCH /api/profiles/me) ───────────────────
    # NULL = never edited; profile_me() then falls back to its mock-derived
    # demo defaults, so untouched profiles read back byte-identically.
    # `location` edits reuse the existing `candidate_location` column above.
    # `profile_skills` is an override list only — the verified
    # `skill_ledger_rows` stay authoritative for /api/skills, scores, and
    # approvals (a free-form profile edit must not clobber verification
    # state, depth, or session counts).
    profile_bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_current_role: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    profile_experience_years: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    profile_skills: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)

    # ── InterviewerStatus, flattened (1:1) ─────────────────────────────────
    interviewer_mode: Mapped[str] = mapped_column(
        Enum(*_INTERVIEWER_MODES, name="interviewer_mode", native_enum=False, create_constraint=True),
        nullable=False,
        default="none",
    )
    interviewer_origin: Mapped[Optional[str]] = mapped_column(
        Enum(*_INTERVIEWER_ORIGINS, name="interviewer_origin", native_enum=False, create_constraint=True),
        nullable=True,
    )
    interviewer_approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    interviewer_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    interviewer_bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # InterviewerStats, flattened (all optional — absent for specialists).
    stats_sessions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stats_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stats_reliability: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stats_peer_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stats_appeal_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stats_average_review_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stats_monthly_earnings: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    skills: Mapped[list["SkillLedgerRow"]] = relationship(
        back_populates="ledger", cascade="all, delete-orphan", lazy="selectin"
    )
    authorities: Mapped[list["InterviewerAuthority"]] = relationship(
        back_populates="ledger", cascade="all, delete-orphan", lazy="selectin"
    )
    # Small, never independently queried list — JSONB, not a child table
    # (unlike `skills`/`authorities` above, which are mutated in place
    # post-creation by approvals_service and stay real tables).
    external_proofs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class SkillLedgerRow(Base):
    __tablename__ = "skill_ledger_rows"
    __table_args__ = (UniqueConstraint("ledger_candidate_id", "skill_id", name="uq_ledger_skill_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # No standalone index: the table's unique constraint leads with this column.
    ledger_candidate_id: Mapped[str] = mapped_column(
        ForeignKey("skill_ledgers.candidate_id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. "skl_001"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(
        Enum(*_SKILL_STATES, name="skill_state", native_enum=False, create_constraint=True),
        nullable=False,
    )
    depth: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_verified: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # soft ref to session_reports.id
    authority: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    authority_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ledger: Mapped["SkillLedger"] = relationship(back_populates="skills")


class InterviewerAuthority(Base):
    __tablename__ = "interviewer_authorities"
    __table_args__ = (
        UniqueConstraint("ledger_candidate_id", "skill_name", name="uq_authority_ledger_skill"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # No standalone index: the table's unique constraint leads with this column.
    ledger_candidate_id: Mapped[str] = mapped_column(
        ForeignKey("skill_ledgers.candidate_id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(String(40), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ledger: Mapped["SkillLedger"] = relationship(back_populates="authorities")
