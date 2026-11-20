"""Ingested assessment transcripts — storage layer.

One row per finished RAW assessment session. The RAW bot-worker POSTs the
full transcript + metadata + (optional) dossier here when a session ends
(see app/api/sessions_ingest.py). This is the raw, append-only record that
"starts the process"; turning it into a verifier report is a separate,
later concern (deliberately not wired here).

Kept separate from `live_sessions` (the copilot UI snapshot) on purpose:
that table has a hard FK to `booking_catalogs` and many NOT NULL identity
columns a service-side ingest can't always supply. This table stores
exactly what RAW sends, nothing it can't.
"""

from typing import Any, Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_INGEST_STATUSES = ("ended", "processing", "reported")


class AssessmentTranscript(Base, TimestampMixin):
    __tablename__ = "assessment_transcripts"

    # The RAW room name == the Anveksha booking/session id (the deep-link
    # contract: room = interviewId). One row per session; re-ingest upserts.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    room: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Soft ref to my_interviews.id when the room is a real booking id; left
    # null for ad-hoc rooms. Not an FK — RAW rooms aren't always bookings.
    booking_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    # Traceability FKs (nullable — RAW ad-hoc rooms may not resolve). Which
    # assessment this session was for, the candidate who took it, and the
    # verifier assigned. Set from the ingest payload's metadata when RAW knows
    # them; a report FKs back to this row via skill_report_details.transcript_id.
    assessment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verifier_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bot_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    response_mode: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ended")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Transcript lines: [{t, who, text}, ...]. participants/metadata/dossier
    # are free-form JSON exactly as RAW sends them. `extra_metadata` maps to
    # a column named "metadata" (the attribute name `metadata` is reserved
    # by SQLAlchemy's Declarative base).
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    participants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    dossier: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
