"""Portal (privacy / dossier / booking) — storage layer.

`Dossier` has no `ledger` column — it FKs to the candidate's live
`skill_ledgers` row via `candidate_id` and the service layer joins at
read time, rather than duplicating a snapshot. Booking's days/slots are
JSONB lists on one catalog row, joined by a shared `day_key` in Python.

`MyInterview.catalog_id` is an intentionally soft (non-FK) reference —
seed data includes demo rows pointing at catalogs that were never fully
seeded. `LiveSessionSnapshot.catalog_id` IS a real FK: every row resolves to `booking_catalogs` and the seeder
is the only writer, so referential integrity is enforceable there.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import ARRAY, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

_DISCOVERABILITY = ("anyone", "verified-only", "invite-only", "private")
_LIVE_STATUSES = ("live", "ended")
_DOSSIER_SESSION_VERDICTS = ("verified", "unverified")
_MY_INTERVIEW_STATUSES = ("scheduled", "completed")


class PrivacySettings(Base, TimestampMixin):
    __tablename__ = "privacy_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    share_profile: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    share_dossiers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    share_transcripts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_gray_followups: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hide_from_companies: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    discoverability: Mapped[str] = mapped_column(
        Enum(*_DISCOVERABILITY, name="privacy_discoverability", native_enum=False, create_constraint=True),
        nullable=False,
        default="verified-only",
    )
    share_score: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    share_gap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    share_gray: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    share_transcript: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_followup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    anonymous_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    share_verifier_panel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Small, never independently queried list — JSONB, not a child table.
    # Each dict carries an `id` key (e.g. "sr_001") that `revoke_shared_report`
    # matches on; `report_id` inside is a soft ref to session_reports.id.
    shared_reports: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class Dossier(Base, TimestampMixin):
    __tablename__ = "dossiers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # References the live skill_ledgers row (see module docstring) rather
    # than duplicating it. Also transitively FK's to users.id, since
    # skill_ledgers.candidate_id does.
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("skill_ledgers.candidate_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_initials: Mapped[str] = mapped_column(String(4), nullable=False)
    candidate_title: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_location: Mapped[str] = mapped_column(String(120), nullable=False)
    years: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verification_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    gray_areas: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    strengths: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sessions: Mapped[list["DossierSession"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", lazy="selectin", order_by="DossierSession.id"
    )


class DossierSession(Base):
    __tablename__ = "dossier_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(String(40), nullable=False)
    date: Mapped[str] = mapped_column(String(40), nullable=False)
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    verifier: Mapped[str] = mapped_column(String(200), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(
        Enum(*_DOSSIER_SESSION_VERDICTS, name="dossier_session_verdict", native_enum=False, create_constraint=True),
        nullable=False,
    )

    dossier: Mapped["Dossier"] = relationship(back_populates="sessions")


class BookingCatalog(Base, TimestampMixin):
    __tablename__ = "booking_catalogs"

    catalog_id: Mapped[str] = mapped_column(String, primary_key=True)
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    depth: Mapped[str] = mapped_column(String(60), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    style: Mapped[str] = mapped_column(String(120), nullable=False)
    format: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    probes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    week_range: Mapped[str] = mapped_column(String(60), nullable=False)

    # Small, never independently queried lists — JSONB, not child tables.
    # `slots` entries carry a `day_key` matching a `days` entry's `day_key`
    # (the old "merge days list + slotsByDay dict" shape), reconstructed
    # in Python at read time — same as before, just no SQL join needed.
    days: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    slots: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class MyInterview(Base, TimestampMixin):
    __tablename__ = "my_interviews"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Owner — services return only the caller's rows.
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    catalog_id: Mapped[str] = mapped_column(String, nullable=False)  # soft ref — see module docstring
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_MY_INTERVIEW_STATUSES, name="my_interview_status", native_enum=False, create_constraint=True),
        nullable=False,
    )
    scheduled_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LiveSessionSnapshot(Base, TimestampMixin):
    __tablename__ = "live_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Real FK, unlike my_interviews.catalog_id — the seeder is the only
    # writer and every row resolves (see module docstring).
    catalog_id: Mapped[str] = mapped_column(
        ForeignKey("booking_catalogs.catalog_id"), nullable=False, index=True
    )
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_LIVE_STATUSES, name="live_session_status", native_enum=False, create_constraint=True),
        nullable=False,
    )
    elapsed_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_initials: Mapped[str] = mapped_column(String(4), nullable=False)
    candidate_color: Mapped[str] = mapped_column(String(20), nullable=False)
    verifier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    verifier_initials: Mapped[str] = mapped_column(String(4), nullable=False)
    verifier_color: Mapped[str] = mapped_column(String(20), nullable=False)
    current_probe: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_probes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    unverified_claim_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unverified_claim_at: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Small, never independently queried lists — JSONB, not child tables.
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    phases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    assessment: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
