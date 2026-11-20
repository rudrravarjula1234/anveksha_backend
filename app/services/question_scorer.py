"""Learning loop: score the questions a bot actually asked, from the
finished transcript, and fold that back into the question bank so good
questions surface more over time.

For each question the bot/verifier asked, Gemini rates how relevant it was
and whether it elicited signal (judged from the candidate's reply that
followed). Each rated question is matched to the nearest bank question by
embedding similarity; its ``quality_score`` moves toward the rating (EWMA),
``avg_signal_score`` and ``times_asked`` update. A strong, unmatched
question is inserted as ``source="learned"`` so the bank grows from real
interviews — including assisted ones.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.agents.embeddings import embed_text
from app.agents.gemini_text import complete_json
from app.models.portal import BookingCatalog, MyInterview
from app.models.question_bank import InterviewQuestion
from app.models.session_ingest import AssessmentTranscript

logger = logging.getLogger(__name__)

_EWMA_ALPHA = 0.3  # how fast quality moves toward a new rating
_MATCH_SIM_FLOOR = 0.80  # cosine >= this → same question; else it's novel

_SCORER_SYSTEM = (
    "You are evaluating an interview transcript to improve a question bank. "
    "For each question the INTERVIEWER asked, judge how good a question it was "
    "for assessing the skill, using the candidate's following reply as evidence "
    "of whether it elicited real signal. Output ONLY JSON: "
    '{"items":[{"question":"<the interviewer question text>",'
    '"relevance":0.0-1.0,"signal":0.0-1.0,"probe_area":"<short area>"}]}. '
    "relevance = how on-topic/useful the question was; signal = how much the "
    "candidate's answer revealed. Include only genuine interviewer questions."
)


async def _resolve_skill(db: AsyncSession, tx: AssessmentTranscript) -> Optional[str]:
    booking_id = tx.booking_id or tx.room
    mi = await db.get(MyInterview, booking_id) if booking_id else None
    if mi and mi.catalog_id:
        cat = await db.get(BookingCatalog, mi.catalog_id)
        if cat:
            from app.services.question_bank_service import resolve_bank_skill

            return await resolve_bank_skill(db, cat.skill_name)
    return None


def _transcript_to_text(transcript: list[dict[str, Any]]) -> str:
    lines = []
    for t in transcript:
        who = t.get("who") or t.get("label") or "?"
        lines.append(f"{who}: {t.get('text', '')}")
    return "\n".join(lines)


async def score_session(db: AsyncSession, session_id: str) -> int:
    """Score one finished session's questions and update the bank. Returns the
    number of bank questions updated/added. Best-effort — raises only on a
    programming error, not on a model hiccup."""
    tx = await db.get(AssessmentTranscript, session_id)
    if tx is None or not tx.transcript:
        return 0
    skill = await _resolve_skill(db, tx)
    if not skill:
        # Fall back to any skill present — scoring is still useful signal,
        # but without a skill we can't match within-skill, so skip.
        logger.info("score_session: no skill resolved for %s — skipping", session_id)
        return 0

    try:
        rated = await complete_json(
            _SCORER_SYSTEM,
            f"Skill: {skill}\n\nTranscript:\n{_transcript_to_text(tx.transcript)[:6000]}",
            max_tokens=1200,
        )
    except Exception:
        logger.exception("scorer model call failed for %s", session_id)
        return 0
    items = (rated or {}).get("items") or []
    if not items:
        return 0

    updated = 0
    for item in items:
        q_text = str(item.get("question") or "").strip()
        if not q_text:
            continue
        relevance = float(item.get("relevance") or 0.0)
        signal = float(item.get("signal") or 0.0)
        try:
            qv = await embed_text(q_text)
        except Exception:
            logger.exception("embed failed while scoring a question")
            continue
        dist = InterviewQuestion.embedding.cosine_distance(qv)
        row = (
            await db.execute(
                select(InterviewQuestion, dist.label("d"))
                .where(InterviewQuestion.skill == skill)
                .order_by(dist)
                .limit(1)
            )
        ).first()
        if row is not None and (1.0 - float(row.d)) >= _MATCH_SIM_FLOOR:
            q = row[0]
            q.quality_score = (1 - _EWMA_ALPHA) * q.quality_score + _EWMA_ALPHA * relevance
            n = q.times_asked
            q.avg_signal_score = (q.avg_signal_score * n + signal) / (n + 1)
            q.times_asked = n + 1
            updated += 1
        else:
            # Novel question the interviewer actually used — learn it.
            db.add(
                InterviewQuestion(
                    id=f"q_{str(ULID()).lower()}",
                    skill=skill,
                    probe_area=str(item.get("probe_area") or "General")[:200],
                    text=q_text,
                    assesses=[],
                    difficulty=3,
                    expected_signals="",
                    embedding=qv,
                    source="learned",
                    quality_score=max(0.5, relevance),
                    times_asked=1,
                    avg_signal_score=signal,
                )
            )
            updated += 1
    await db.flush()
    logger.info("score_session %s: updated/added %d questions (skill=%s)", session_id, updated, skill)
    return updated
