"""Candidate portal — storage layer.

`skill_reports`, `skill_report_details`, `insights`, `session_history`,
and `notifications` all carry a NOT NULL `user_id` FK — services filter
by the requesting caller, so one candidate never sees another's data.
`onboarding_steps` (a global wizard) and `public_profiles` (already
keyed by `userId`) are unaffected.
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
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_REPORT_STATUSES = ("published", "in-review", "draft")
_ASSESSMENT_TYPES = ("live", "bot", "bot-assisted")
_INSIGHT_KINDS = ("follow-up", "gap", "momentum", "integrity")
_SESSION_STATUSES = ("published", "archived", "in-review")
_NOTIFICATION_KINDS = ("session", "dossier", "company", "followup", "integrity")


class SkillReport(Base, TimestampMixin):
    __tablename__ = "skill_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable — not every summary row has a full detail record yet (e.g.
    # a report a verifier hasn't published a full write-up for). Links the
    # summary and full-detail views of what's otherwise the same report;
    # `skill`/`verifier`/`date` below stay separate columns rather than
    # being derived via join because they're independently-formatted per
    # surface (e.g. `verifier` here is abbreviated, `skill_report_details.
    # verifier_name` is the full name), not pure duplication.
    report_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("skill_report_details.id", ondelete="SET NULL"), nullable=True, index=True
    )
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    verifier: Mapped[str] = mapped_column(String(200), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_REPORT_STATUSES, name="skill_report_status", native_enum=False, create_constraint=True),
        nullable=False,
    )
    companies_viewed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SkillReportDetail(Base, TimestampMixin):
    __tablename__ = "skill_report_details"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(40), nullable=False)
    assessment_title: Mapped[str] = mapped_column(String(200), nullable=False)
    # ReportParty / ReportVerifier — 1:1, flattened.
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_ext_id: Mapped[str] = mapped_column(String(40), nullable=False)
    verifier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    verifier_ext_id: Mapped[str] = mapped_column(String(40), nullable=False)
    verifier_title: Mapped[str] = mapped_column(String(200), nullable=False)
    verifier_rating: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[str] = mapped_column(String(40), nullable=False)
    duration: Mapped[str] = mapped_column(String(40), nullable=False)
    type: Mapped[str] = mapped_column(
        Enum(*_ASSESSMENT_TYPES, name="report_detail_type", native_enum=False, create_constraint=True),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[str] = mapped_column(String(60), nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_long: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Small (3-7 row), never independently queried lists — JSONB, not child
    # tables. Each dict's keys match the old child table's column names.
    fit_signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    phases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    gaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    gray: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class CandidateInsight(Base, TimestampMixin):
    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        Enum(*_INSIGHT_KINDS, name="insight_kind", native_enum=False, create_constraint=True), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(String(60), nullable=False)
    companies: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    acted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class OnboardingStep(Base, TimestampMixin):
    """Global wizard steps — NOT per-user (only one seeded set, shared by
    every candidate); see the module docstring for why this one wasn't
    included in the per-user scoping fix."""

    __tablename__ = "onboarding_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PublicProfile(Base, TimestampMixin):
    __tablename__ = "public_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    share_url: Mapped[str] = mapped_column(Text, nullable=False)
    anv_id: Mapped[str] = mapped_column(String(40), nullable=False)
    last_updated: Mapped[str] = mapped_column(String(40), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_companies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inbound_chats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    about: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Small, never independently queried lists — JSONB, not child tables.
    highlights: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    constellation: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    gray_areas: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class SessionHistoryRow(Base, TimestampMixin):
    __tablename__ = "session_history"
    __table_args__ = (
        # Matches the history query: WHERE user_id = ? ORDER BY created_at DESC LIMIT n.
        Index("ix_session_history_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Nullable — not every history entry has a full report (e.g. an
    # archived/superseded session). See SkillReport.report_id.
    report_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("skill_report_details.id", ondelete="SET NULL"), nullable=True, index=True
    )
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[str] = mapped_column(String(40), nullable=False)
    duration: Mapped[str] = mapped_column(String(40), nullable=False)
    verifier: Mapped[str] = mapped_column(String(200), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_SESSION_STATUSES, name="session_history_status", native_enum=False, create_constraint=True),
        nullable=False,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppNotification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        # Matches the inbox query: WHERE user_id = ? ORDER BY created_at DESC LIMIT n.
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(
        Enum(*_NOTIFICATION_KINDS, name="notification_kind", native_enum=False, create_constraint=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # "createdAt" on the wire
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    href: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
