"""Ingest endpoint for finished RAW assessment sessions.

The RAW bot-worker POSTs the full transcript + metadata + optional dossier
here when a session ends (service-key auth — no logged-in user behind a
bot-worker shutdown callback). This stores the raw record and returns; it
is the single "call that starts the process". Turning the transcript into a
verifier report is deliberately a separate, later concern.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import require_service_key
from app.db.session import get_session
from app.schemas.base import AppModel, ReadModel
from app.services.session_ingest_service import SessionIngestService

router = APIRouter(tags=["Sessions (ingest)"], dependencies=[Depends(require_service_key)])


class TranscriptLineIn(AppModel):
    t: str = ""  # timestamp label, e.g. "02:14"
    who: str = ""  # speaker role: "candidate" | "bot" | "verifier"
    text: str = ""
    label: str = ""  # human-readable speaker, e.g. "Candidate (Sai)" or the bot name


class TranscriptIngest(AppModel):
    room: Optional[str] = None
    bookingId: Optional[str] = None
    botId: Optional[str] = None
    responseMode: Optional[str] = None
    durationMs: int = 0
    transcript: list[TranscriptLineIn] = Field(default_factory=list)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dossier: Optional[dict[str, Any]] = None


class IngestAck(ReadModel):
    id: str
    status: str
    turnCount: int


async def _score_session_bg(session_id: str) -> None:
    """Background: learn from the finished session — score the questions the
    bot asked and fold the ratings back into the bank. Its own DB session
    (the request's is closed by the time this runs); never raises outward."""
    from app.db.session import get_sessionmaker
    from app.services.question_scorer import score_session

    try:
        async with get_sessionmaker()() as db:
            await score_session(db, session_id)
            await db.commit()
    except Exception:  # noqa: BLE001 - a learning hiccup must not matter
        logging.getLogger(__name__).exception("background scoring failed for %s", session_id)


@router.post(
    "/{session_id}/transcript",
    response_model=IngestAck,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_transcript(
    session_id: str,
    payload: TranscriptIngest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> IngestAck:
    row = await SessionIngestService(db).ingest(
        session_id=session_id,
        room=payload.room,
        booking_id=payload.bookingId,
        bot_id=payload.botId,
        response_mode=payload.responseMode,
        duration_ms=payload.durationMs,
        transcript=[line.model_dump() for line in payload.transcript],
        participants=payload.participants,
        metadata=payload.metadata,
        dossier=payload.dossier,
    )
    # Learn from this session without blocking the ack.
    background.add_task(_score_session_bg, row.id)
    return IngestAck(id=row.id, status=row.status, turnCount=row.turn_count)
