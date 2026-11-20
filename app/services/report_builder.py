"""Turn a finished RAW transcript into a verifier report.

The missing bridge between `assessment_transcripts` (what RAW ingests) and
`pending_reports` / `session_reports` (what the SME console reviews). On
ingest of a *traceable* session (one that resolved to a real candidate),
this builds the SME's working copy: one `PendingReport` (queue row) plus one
draft `SessionReport` whose sections are derived from the actual transcript
turns, carrying the bot's provisional per-section score. The SME then edits
`verifier_score`; the gap between the two is the "variance" Scene 3 surfaces.

Idempotent: re-ingesting the same session id upserts the report in place
(the bot can only end a session once, but a retried POST must not duplicate).
Keyed by the session id so the pending row, the report, and the transcript
all share one id and stay joinable without a new FK.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.models.session_ingest import AssessmentTranscript
from app.models.user import User
from app.models.verifier import PendingReport, SessionReport


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "–"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _verdict_for(score: float) -> str:
    if score >= 75:
        return "verified"
    if score >= 50:
        return "partial"
    return "gray"


def _score_answer(answer: str, dossier_score: Optional[float]) -> int:
    """Bot's provisional score for one answered probe.

    Prefers a score RAW's dossier carries; otherwise a transparent heuristic
    over answer substance (longer, more-developed answers score higher). This
    is the bot's first pass on purpose — the SME's manual score is what it
    gets measured against (the variance), so it only has to exist and be
    traceable to the real answer text, not be authoritative.
    """
    if dossier_score is not None:
        return int(max(0, min(100, round(dossier_score))))
    words = len([w for w in answer.split() if w])
    return int(max(50, min(95, 60 + words)))


def _sections_from_transcript(
    turns: list[dict[str, Any]], dossier: Optional[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pair each bot question with the candidate's next answer into one
    report section, scored and quoting the real answer as evidence."""
    dossier_scores = {}
    if dossier and isinstance(dossier.get("scores"), dict):
        dossier_scores = dossier["scores"]

    sections: list[dict[str, Any]] = []
    pending_q: Optional[str] = None
    for turn in turns:
        who = (turn.get("who") or "").lower()
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        if who in ("bot", "assistant", "interviewer", "ai"):
            # A new probe — the prior unanswered one (if any) gets no section.
            pending_q = text
        elif who in ("candidate", "user"):
            if pending_q is None:
                continue
            idx = len(sections) + 1
            title = pending_q if len(pending_q) <= 90 else pending_q[:87] + "…"
            score = _score_answer(text, dossier_scores.get(str(idx)))
            sections.append(
                {
                    "section_id": f"sec_{idx}",
                    "title": title,
                    "ai_score": score,
                    "verifier_score": None,  # SME fills this in — drives variance
                    "notes": "",
                    "evidence": [text if len(text) <= 400 else text[:397] + "…"],
                }
            )
            pending_q = None
    return sections


async def _candidate_name(db: AsyncSession, user_id: Optional[str]) -> str:
    if not user_id:
        return "Candidate"
    user = await db.get(User, user_id)
    if user is None:
        return "Candidate"
    name = f"{user.first_name} {user.last_name}".strip()
    return name or "Candidate"


async def _skill_label(
    db: AsyncSession, assessment_id: Optional[str], meta: dict[str, Any], bot_id: Optional[str]
) -> str:
    if assessment_id:
        asm = await db.get(Assessment, assessment_id)
        if asm is not None and asm.title:
            return asm.title
    return meta.get("skill") or meta.get("assessmentTitle") or bot_id or "Assessment"


async def build_report_from_transcript(
    db: AsyncSession, row: AssessmentTranscript
) -> Optional[SessionReport]:
    """Create/upsert the SME's pending report + draft session report from a
    just-ingested transcript. Returns None (no report) for untraceable rooms
    — an ad-hoc session with no candidate isn't a reviewable assessment."""
    if not row.candidate_user_id:
        return None

    turns = row.transcript or []
    sections = _sections_from_transcript(turns, row.dossier)
    if not sections:
        # Nothing the candidate actually answered — no report to review yet.
        return None

    candidate = await _candidate_name(db, row.candidate_user_id)
    skill = await _skill_label(db, row.assessment_id, row.extra_metadata or {}, row.bot_id)

    ai_scores = [s["ai_score"] for s in sections]
    overall = round(sum(ai_scores) / len(ai_scores))
    verdict = _verdict_for(overall)
    now = datetime.now(timezone.utc)
    # Short, real date label for the queue row (what the seed rows use).
    date_label = now.strftime("%b %d, %Y")

    strengths = []
    gray_areas = []
    if row.dossier:
        strengths = list(row.dossier.get("strengths") or [])
        gray_areas = list(row.dossier.get("grayAreas") or row.dossier.get("gray_areas") or [])

    # ── Pending queue row (upsert) ──────────────────────────────────────
    pending = await db.get(PendingReport, row.id)
    if pending is None:
        pending = PendingReport(id=row.id)
        db.add(pending)
    pending.session_id = row.id
    pending.candidate = candidate
    pending.initials = _initials(candidate)
    pending.skill = skill
    pending.date = date_label
    pending.ai_score = overall

    # ── Draft session report (upsert) ───────────────────────────────────
    report = await db.get(SessionReport, row.id)
    if report is None:
        report = SessionReport(id=row.id, report_created_at=now)
        db.add(report)
    report.session_id = row.id
    report.candidate_name = candidate
    report.skill = skill
    report.verdict = verdict
    report.overall_score = overall
    report.gray_areas = gray_areas
    report.strengths = strengths
    report.status = "review"
    report.sections = sections

    # Mark the transcript as having produced a report (status lifecycle).
    row.status = "reported"

    await db.flush()
    return report
