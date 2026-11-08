"""Company portal — storage layer.

Credit balance is a maintained column on `companies`, updated in the same
transaction as each `credit_transactions` insert rather than recomputed
by scanning the ledger; month-to-date figures are SQL aggregates.

`search_candidates` ids (`cand_001`, ...) are the company's talent-pool
view, not platform `users.id`s — `gray_followups`, `company_unlocks`,
and `pipeline_cards` all FK into `search_candidates`, not `users`.

Single-tenant by decision (launch scope): there is one `companies` row and
none of the portal tables below carry a `company_id`. Going multi-company
means adding a `company_id` FK to each of them (and `(company_id,
candidate_id)` PKs on `company_unlocks` / `pipeline_cards`) plus a backfill.
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
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_TX_KINDS = ("earned", "spent")
_TEAM_ROLES = ("Hiring Manager", "Recruiter", "Viewer")
_MEMBER_STATUSES = ("active", "inactive")
_BILLING_PLANS = ("Starter", "Growth", "Enterprise")
_FOLLOWUP_STATUSES = ("pending", "requested", "accepted", "completed", "declined")
_PIPELINE_STAGES = ("investigating", "followup", "shortlist", "offered")


class Company(Base, TimestampMixin):
    """Singleton (`id = "co_northstack"` — the one company this demo
    backend serves)."""

    __tablename__ = "companies"
    # Backstop for the conditional UPDATE in company_service._apply_tx.
    __table_args__ = (CheckConstraint("credit_balance >= 0", name="ck_companies_credit_balance_nonneg"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_domain: Mapped[str] = mapped_column(String(200), nullable=False)
    # Maintained credit balance — see module docstring.
    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AnonymousInterviewer(Base, TimestampMixin):
    __tablename__ = "anonymous_interviewers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    specialties: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    external_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreditTransaction(Base, TimestampMixin):
    __tablename__ = "credit_transactions"
    __table_args__ = (
        # Matches _month_sum()'s (kind, at range) query shape.
        Index("ix_credit_transactions_kind_at", "kind", "at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Real timestamp, not a string — the original Mongo-era code parsed
    # `at` into a datetime before every comparison specifically to dodge
    # "Z" vs "+00:00" suffix mismatches; storing it as a real column
    # fixes that at the source instead of hoping string formats agree.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        Enum(*_TX_KINDS, name="credit_tx_kind", native_enum=False, create_constraint=True), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    interviewer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("anonymous_interviewers.id", ondelete="SET NULL"), nullable=True, index=True
    )


class CreditRate(Base, TimestampMixin):
    """Singleton (`id = "default"`)."""

    __tablename__ = "credit_rate"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    # Numeric, not Float — a real currency conversion rate; asdecimal=False
    # keeps the Python-side value a plain float.
    rupees_per_credit: Mapped[float] = mapped_column(Numeric(10, 4, asdecimal=False), nullable=False)
    # When the rate itself last changed ("updatedAt" on the wire) — kept
    # apart from TimestampMixin.updated_at, which any row write bumps.
    rate_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)


class TeamMember(Base, TimestampMixin):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(*_TEAM_ROLES, name="team_role", native_enum=False, create_constraint=True), nullable=False
    )
    pipelines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        Enum(*_MEMBER_STATUSES, name="team_member_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="active",
    )


class Billing(Base, TimestampMixin):
    """Singleton (`id = "default"`)."""

    __tablename__ = "billing"
    __table_args__ = (CheckConstraint("seats_used <= seats", name="ck_billing_seats_used_le_seats"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    plan: Mapped[str] = mapped_column(
        Enum(*_BILLING_PLANS, name="billing_plan", native_enum=False, create_constraint=True), nullable=False
    )
    seats: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_used: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    next_billing: Mapped[str] = mapped_column(String(40), nullable=False)
    includes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    ai_chats_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_chats_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Small, never independently queried list — JSONB, not a child table.
    invoices: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class GrayFollowup(Base, TimestampMixin):
    __tablename__ = "gray_followups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("search_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gray_area: Mapped[str] = mapped_column(String(200), nullable=False)
    asked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_FOLLOWUP_STATUSES, name="gray_followup_status", native_enum=False, create_constraint=True),
        nullable=False,
    )
    companies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class SearchCandidate(Base, TimestampMixin):
    __tablename__ = "search_candidates"
    __table_args__ = (
        # Backs company_service.search()'s SQL-side `minScore` filter.
        Index("ix_search_candidates_verification_score", "verification_score"),
        CheckConstraint("verification_score BETWEEN 0 AND 100", name="ck_search_candidates_verification_score"),
        CheckConstraint("match_percent BETWEEN 0 AND 100", name="ck_search_candidates_match_percent"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    initials: Mapped[str] = mapped_column(String(4), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    years: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    verification_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    match_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    gray_skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    last_activity: Mapped[str] = mapped_column(String(60), nullable=False, default="")


class CompanyUnlock(Base, TimestampMixin):
    __tablename__ = "company_unlocks"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("search_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SearchFacets(Base, TimestampMixin):
    """Singleton (`id = "default"`) — a display-computed aggregate with no
    cross-references, so it stays JSONB rather than decomposed tables."""

    __tablename__ = "search_facets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    locations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class PipelineCard(Base, TimestampMixin):
    __tablename__ = "pipeline_cards"
    __table_args__ = (CheckConstraint("match_percent BETWEEN 0 AND 100", name="ck_pipeline_cards_match_percent"),)

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("search_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    initials: Mapped[str] = mapped_column(String(4), nullable=False)
    match_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_activity: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    stage: Mapped[str] = mapped_column(
        Enum(*_PIPELINE_STAGES, name="pipeline_stage", native_enum=False, create_constraint=True), nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FollowupSkillOption(Base, TimestampMixin):
    __tablename__ = "followup_skills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FollowupRequest(Base, TimestampMixin):
    __tablename__ = "followup_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("search_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # "createdAt" on the wire
