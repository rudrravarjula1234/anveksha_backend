"""Interviewer approvals — storage layer.

`approve()` (see `app.services.approvals_service`) touches three tables
— the approval row, `active_interviewers`, and the candidate's
`skill_ledgers` authority grant — atomically, in one request transaction.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_APPROVAL_STATUSES = ("pending", "approved", "rejected")
_APPROVAL_ORIGINS = ("bot-discovered", "self-requested")
_INVITE_STATUSES = ("sent", "accepted", "expired")
_ACTIVE_MODES = ("freelance", "specialist")


class InterviewerApproval(Base, TimestampMixin):
    __tablename__ = "interviewer_approvals"
    __table_args__ = (
        # At most one open request per candidate + skill. The service's
        # pre-insert check gives the friendly 409; this closes the race
        # between two concurrent submissions.
        Index(
            "uq_interviewer_approvals_pending_skill",
            "candidate_id",
            "requested_skill",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        # Backs the overview's "recent decisions" read: scanned backwards it
        # yields ORDER BY reviewed_at DESC, id DESC with no sort step.
        Index(
            "ix_interviewer_approvals_decided",
            "reviewed_at",
            "id",
            postgresql_where=text("status <> 'pending'"),
        ),
        # A decided request always records when: the newest-first read puts
        # NULLs first, so an undated decision would sit on top forever.
        CheckConstraint(
            "status = 'pending' OR reviewed_at IS NOT NULL", name="ck_interviewer_approvals_decided_reviewed_at"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Deliberately NOT a hard FK to users.id: bot-discovered candidates can
    # be flagged for review before they're registered users at all (the
    # seed data includes pending requests for candidates outside the demo
    # persona roster) — same soft-reference semantics the original Mongo
    # design had, kept intentionally rather than by default this time.
    candidate_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_initials: Mapped[str] = mapped_column(String(4), nullable=False)
    dossier_id: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_skill: Mapped[str] = mapped_column(String(200), nullable=False)
    origin: Mapped[str] = mapped_column(
        Enum(*_APPROVAL_ORIGINS, name="approval_origin", native_enum=False, create_constraint=True),
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_APPROVAL_STATUSES, name="approval_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="pending",
        index=True,
    )
    candidate_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    candidate_sessions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bot_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SpecialistInvite(Base, TimestampMixin):
    __tablename__ = "specialist_invites"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        Enum(*_INVITE_STATUSES, name="invite_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="sent",
    )
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_by: Mapped[str] = mapped_column(String, nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Small, never independently queried list — JSONB, not a child table.
    external_proofs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class ActiveInterviewer(Base, TimestampMixin):
    __tablename__ = "active_interviewers"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_initials: Mapped[str] = mapped_column(String(4), nullable=False)
    mode: Mapped[str] = mapped_column(
        Enum(*_ACTIVE_MODES, name="active_interviewer_mode", native_enum=False, create_constraint=True),
        nullable=False,
    )
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reliability: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Small, never independently queried list — JSONB, not a child table.
    # `_grant_authority()` reassigns the whole list to append (not an
    # in-place mutation) so SQLAlchemy's change tracking sees it.
    authorities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
