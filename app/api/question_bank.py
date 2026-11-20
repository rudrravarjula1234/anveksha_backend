"""Smart-interviewer endpoints: next-probe retrieval over the question bank.

Called by the RAW bot-worker (service-key auth — no logged-in user). Given
the running session's skill (resolved from the room when only a room id is
sent) plus what's been asked / covered / how much time is left, returns the
single next question the bot should ask, chosen by the graph-RAG policy.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import require_service_key
from app.db.session import get_session
from app.models.portal import BookingCatalog, MyInterview
from app.models.question_bank import InterviewQuestion
from app.models.session_ingest import AssessmentTranscript
from app.schemas.base import AppModel, ReadModel
from app.services.question_bank_service import QuestionBankService, resolve_bank_skill

router = APIRouter(tags=["Bots (question bank)"], dependencies=[Depends(require_service_key)])


class NextProbeRequest(AppModel):
    # Either skill directly, or a room id to resolve it from.
    skill: Optional[str] = None
    room: Optional[str] = None
    lastAnswer: str = ""
    askedQuestionIds: list[str] = []
    coveredAreas: list[str] = []
    secondsRemaining: Optional[int] = None


class NextProbeResponse(ReadModel):
    questionId: Optional[str]
    question: str
    probeArea: str
    assesses: list[str]
    difficulty: int
    rationale: str
    action: str
    skill: str


async def _resolve_skill(db: AsyncSession, *, skill: Optional[str], room: Optional[str]) -> Optional[str]:
    if skill:
        return skill
    if not room:
        return None
    # room == my_interviews.id → catalog_id → booking_catalogs.skill_name
    mi = await db.get(MyInterview, room)
    if mi and mi.catalog_id:
        cat = await db.get(BookingCatalog, mi.catalog_id)
        if cat:
            return cat.skill_name
    # Fallback: the ingested transcript's booking_id, else the bot's first
    # specialization isn't reachable here without the bot row — use any
    # question-bank skill the room's transcript was tagged with.
    tx = await db.get(AssessmentTranscript, room)
    if tx and tx.booking_id:
        mi = await db.get(MyInterview, tx.booking_id)
        if mi and mi.catalog_id:
            cat = await db.get(BookingCatalog, mi.catalog_id)
            if cat:
                return cat.skill_name
    return None


@router.post("/next-probe", response_model=NextProbeResponse)
async def next_probe(
    payload: NextProbeRequest, db: AsyncSession = Depends(get_session)
) -> NextProbeResponse:
    skill = await _resolve_skill(db, skill=payload.skill, room=payload.room)
    if not skill:
        # Last resort: if the bank has any questions, use the most common
        # skill so the bot still gets a real question rather than erroring.
        row = (await db.execute(select(InterviewQuestion.skill).limit(1))).scalar_one_or_none()
        skill = row or "General"

    # Align the free-text skill to the bank's skill key (titles vs
    # catalog skill_name rarely match exactly).
    skill = await resolve_bank_skill(db, skill)

    probe = await QuestionBankService(db).plan_next(
        skill=skill,
        last_answer=payload.lastAnswer,
        asked_ids=payload.askedQuestionIds,
        covered_areas=payload.coveredAreas,
        seconds_remaining=payload.secondsRemaining,
    )
    return NextProbeResponse(skill=skill, **probe.as_dict())
