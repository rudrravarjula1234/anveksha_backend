"""Verifier console — storage layer.

`verifier_sessions` uses a `lane` discriminator column (live / upcoming /
completed) instead of three separate embedded lists. The queue's stats
tile (rating/sessions/reliability/earnings) has no table of its own — it's
assembled by `VerifierService.queue()` from the `verifier_console_state`
row, which owns those facts, rather than storing a fourth redundant copy.

Single-verifier by decision (launch scope): none of these tables carry a
`verifier_id`, and the console state is one `id = "default"` row. Going
multi-verifier means adding a `verifier_id` FK to `users.id` on each table
(and keying `verifier_console_state` by it) plus a backfill.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_LANES = ("live", "upcoming", "completed")
_SESSION_STATUSES = ("live", "scheduled", "completed")
_REPORT_VERDICTS = ("verified", "partial", "gray")
_REPORT_STATUSES = ("draft", "review", "published")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


class VerifierSession(Base, TimestampMixin):
    __tablename__ = "verifier_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    lane: Mapped[str] = mapped_column(
        Enum(*_LANES, name="verifier_session_lane", native_enum=False, create_constraint=True),
        nullable=False,
        index=True,
    )
    raw_id: Mapped[str] = mapped_column(String, nullable=False)
    time: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_initials: Mapped[str] = mapped_column(String(4), nullable=False)
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_SESSION_STATUSES, name="verifier_session_status", native_enum=False, create_constraint=True),
        nullable=False,
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    depth: Mapped[str] = mapped_column(String(60), nullable=False, default="")


class VerifierConsoleState(Base, TimestampMixin):
    """Single row (`id = "default"`) holding the one verifier's console
    state: next-session brief, governance metrics, earnings, and profile.

    Merged from the four former singletons `verifier_brief`,
    `verifier_governance`, `verifier_earnings`, `verifier_profile`:
    same entity, same seed-once lifecycle,
    read together per request (`queue()` fetched three of the four), one
    runtime write path (`update_profile()`, profile columns only), no FKs
    into them. Multi-verifier support later swaps the PK for the
    caller's user id without touching the API layer. Section comments
    below mark which former table each column set came from.
    """

    __tablename__ = "verifier_console_state"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")

    # ── former verifier_brief ──────────────────────────────────────────
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    candidate: Mapped[str] = mapped_column(String(200), nullable=False)
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prioritized_probes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    gray_requested: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # ── former verifier_governance ─────────────────────────────────────
    reliability: Mapped[int] = mapped_column(Integer, nullable=False)
    score_variance: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_rating: Mapped[float] = mapped_column(Float, nullable=False)
    appeal_rate: Mapped[float] = mapped_column(Float, nullable=False)
    average_review_time_min: Mapped[int] = mapped_column(Integer, nullable=False)
    # Current-month earnings is NOT duplicated here — see module docstring;
    # `governance()` reads it from the earnings section's `current_amount`.

    # Small, never independently queried lists — JSONB, not child tables.
    # `recent_reports` entries carry a soft `session_report_id` key (not a
    # DB FK — JSONB can't enforce one) linking back to `session_reports.id`.
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    recent_reports: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # ── former verifier_earnings ───────────────────────────────────────
    current_month: Mapped[str] = mapped_column(String(40), nullable=False)
    current_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    current_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    ytd_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    ytd_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_standard: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_advanced: Mapped[int] = mapped_column(Integer, nullable=False)
    pending: Mapped[int] = mapped_column(Integer, nullable=False)

    # Small, never independently queried lists — JSONB, not child tables.
    months: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    rate_card: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # ── former verifier_profile ────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    years_experience: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="")
    linkedin: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    specializations: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    pending_reports: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Small, never independently queried list — JSONB, not child tables.
    quality: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class PendingReport(Base, TimestampMixin):
    __tablename__ = "pending_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    candidate: Mapped[str] = mapped_column(String(200), nullable=False)
    initials: Mapped[str] = mapped_column(String(4), nullable=False)
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[str] = mapped_column(String(40), nullable=False)
    ai_score: Mapped[int] = mapped_column(Integer, nullable=False)


class SessionReport(Base, TimestampMixin):
    __tablename__ = "session_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    verdict: Mapped[str] = mapped_column(
        Enum(*_REPORT_VERDICTS, name="session_report_verdict", native_enum=False, create_constraint=True),
        nullable=False,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    gray_areas: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    strengths: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        Enum(*_REPORT_STATUSES, name="session_report_status", native_enum=False, create_constraint=True),
        nullable=False,
        index=True,
    )
    report_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # "createdAt" on the wire
    # Nullable — the verifier's own working/lifecycle copy of a report
    # (draft/review/published) is a distinct entity from the candidate-facing
    # published artifact; set once a matching skill_report_details row
    # exists, so `publish_report()` has something to keep in sync.
    published_report_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("skill_report_details.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Small, never independently queried list — JSONB, not a child table.
    # `patch_report()` replaces this wholesale on every section edit anyway.
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class SuggestedGap(Base, TimestampMixin):
    """Flat list — the old Mongo doc wrapped these in one singleton with
    a `gaps` array; no per-report association in the source data."""

    __tablename__ = "verifier_suggested_gaps"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sub: Mapped[str] = mapped_column(Text, nullable=False, default="")
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class VerifierSlot(Base, TimestampMixin):
    __tablename__ = "verifier_slots"
    __table_args__ = (CheckConstraint("duration IN (30, 60, 90)", name="verifier_slot_duration"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    day: Mapped[str] = mapped_column(
        Enum(*_WEEKDAYS, name="verifier_slot_day", native_enum=False, create_constraint=True), nullable=False
    )
    time: Mapped[str] = mapped_column(String(20), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    booked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candidate: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
