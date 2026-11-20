"""Write-side for ingested RAW assessment transcripts.

Upserts one `assessment_transcripts` row per session (keyed by the RAW room
name == the Anveksha booking/session id). Re-ingesting the same session id
overwrites — a session can only end once, but a retried POST must be
idempotent, not a duplicate.
"""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_ingest import AssessmentTranscript


class SessionIngestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest(
        self,
        *,
        session_id: str,
        room: Optional[str],
        booking_id: Optional[str],
        bot_id: Optional[str],
        response_mode: Optional[str],
        duration_ms: int,
        transcript: list[dict[str, Any]],
        participants: list[dict[str, Any]],
        metadata: dict[str, Any],
        dossier: Optional[dict[str, Any]],
    ) -> AssessmentTranscript:
        row = await self.db.get(AssessmentTranscript, session_id)
        if row is None:
            row = AssessmentTranscript(id=session_id)
            self.db.add(row)
        row.room = room or session_id
        row.booking_id = booking_id
        row.bot_id = bot_id
        row.response_mode = response_mode
        row.duration_ms = duration_ms
        row.turn_count = len(transcript)
        row.transcript = transcript
        row.participants = participants
        row.extra_metadata = metadata or {}
        row.dossier = dossier
        # Traceability: RAW carries the resolved assessment/candidate/verifier
        # ids in the session metadata (it knows them from the deep-link that
        # launched the room). Persist them as real FKs so a transcript traces
        # back to its assessment, candidate and verifier. Absent keys leave the
        # columns null (ad-hoc rooms), exactly as before.
        meta = metadata or {}
        row.assessment_id = meta.get("assessmentId") or meta.get("assessment_id")
        row.candidate_user_id = meta.get("candidateUserId") or meta.get("candidate_user_id")
        row.verifier_user_id = meta.get("verifierUserId") or meta.get("verifier_user_id")

        # Fallback: RAW's bot-worker doesn't thread the assessment/candidate ids
        # into its transcript POST yet, so when the room is a real booking
        # (room == interviewId == my_interviews.id) resolve them from the
        # booking instead. Keeps every real-session transcript traceable to its
        # assessment + candidate without a RAW-side change.
        if not row.assessment_id or not row.candidate_user_id:
            from app.models.portal import MyInterview

            booking = await self.db.get(MyInterview, booking_id or session_id)
            if booking is not None:
                row.assessment_id = row.assessment_id or booking.assessment_id or booking.catalog_id
                row.candidate_user_id = row.candidate_user_id or booking.user_id

        row.status = "ended"
        await self.db.flush()

        # Bridge to the SME console: a traceable session becomes a pending
        # report the verifier reviews (sections built from the real transcript
        # turns, carrying the bot's provisional score). Untraceable ad-hoc
        # rooms build nothing. Never let report-building fail the ingest — the
        # transcript is already safely stored above.
        try:
            from app.services.report_builder import build_report_from_transcript

            await build_report_from_transcript(self.db, row)
        except Exception:  # noqa: BLE001 — a report hiccup must not drop the transcript
            import logging

            logging.getLogger(__name__).exception(
                "report build failed for session %s", session_id
            )

        return row
