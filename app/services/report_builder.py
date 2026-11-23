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

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.models.session_ingest import AssessmentTranscript
from app.models.user import User
from app.models.verifier import PendingReport, SessionReport

logger = logging.getLogger(__name__)

# Hard cap on the report-scoring LLM call. When the model is up a real call
# returns in a few seconds; when it's overloaded/unreachable this keeps
# transcript ingest and the SME's publish responsive (deterministic fallback).
_AGENT_SCORE_TIMEOUT = 12.0


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


def _parse_report_json(text: Optional[str]) -> Optional[dict[str, Any]]:
    """Tolerantly parse the report_generator agent's output into a dict —
    strips ```json fences and extracts the first {...} block. None if it isn't
    usable JSON (caller then keeps the deterministic transcript scoring)."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    match = re.search(r"\{.*\}", s, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None
    return obj if isinstance(obj, dict) else None


async def _agent_report(
    db: AsyncSession, skill: str, candidate: str,
    turns: list[dict[str, Any]], sections: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Ask the `report_generator` agent to score the transcript and return a
    structured report. Only used when the agent produced a real (LLM) answer
    — a `fallback`-sourced prose string is ignored so the caller keeps the
    deterministic transcript scoring instead. Best-effort: None on any error."""
    import asyncio

    try:
        from app.services.agent_registry_service import AgentRegistryService

        context = {
            "task": "Score the candidate's demonstrated skill strictly from the transcript and return the structured JSON report.",
            "skill": skill,
            "candidate": candidate,
            "sections": [{"section_id": s["section_id"], "question": s["title"]} for s in sections],
            "transcript": [
                {"t": t.get("t", ""), "who": t.get("who", ""), "text": t.get("text", "")}
                for t in turns
                if (t.get("text") or "").strip()
            ],
        }
        # Cap the wait so a slow/overloaded LLM can't stall transcript ingest
        # or the SME's publish — we fall back to deterministic scoring fast.
        result = await asyncio.wait_for(
            AgentRegistryService(db).run_agent("report_generator", context),
            timeout=_AGENT_SCORE_TIMEOUT,
        )
        if result is not None and getattr(result, "source", None) == "agent":
            return _parse_report_json(result.output)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        logger.warning("report_generator agent unavailable — using deterministic scoring")
    return None


async def generate_report_from_transcript(
    db: AsyncSession, row: AssessmentTranscript
) -> Optional[dict[str, Any]]:
    """The report Agent's authoritative pass over one transcript. Pairs each
    question with its answer, then has `report_generator` (real LLM when a
    provider credential is configured; deterministic `_sections_from_transcript`
    heuristic otherwise) score every section, pick a verdict, and surface
    strengths + gap areas — all grounded in the actual answers.

    Returns a normalized dict (sections / overall_score / verdict / strengths /
    gray_areas / candidate / skill) or None when the session has no answered
    section to score."""
    turns = row.transcript or []
    sections = _sections_from_transcript(turns, row.dossier)
    if not sections:
        return None

    candidate = await _candidate_name(db, row.candidate_user_id)
    skill = await _skill_label(db, row.assessment_id, row.extra_metadata or {}, row.bot_id)

    strengths: list[str] = []
    gray_areas: list[str] = []
    if row.dossier:
        strengths = list(row.dossier.get("strengths") or [])
        gray_areas = list(row.dossier.get("grayAreas") or row.dossier.get("gray_areas") or [])

    parsed = await _agent_report(db, skill, candidate, turns, sections)
    verdict_hint = ""
    if parsed:
        by_id: dict[str, dict[str, Any]] = {}
        for i, a in enumerate(parsed.get("sections") or []):
            if not isinstance(a, dict):
                continue
            sid = a.get("section_id") or (sections[i]["section_id"] if i < len(sections) else None)
            if sid:
                by_id[str(sid)] = a
        for s in sections:
            a = by_id.get(s["section_id"])
            if not a:
                continue
            sc = a.get("ai_score")
            if isinstance(sc, (int, float)):
                s["ai_score"] = int(max(0, min(100, round(sc))))
            if a.get("notes"):
                s["notes"] = str(a["notes"])[:300]
            ev = a.get("evidence")
            if ev:
                s["evidence"] = [str(ev)[:400]] if isinstance(ev, str) else [str(x)[:400] for x in ev][:2]
        p_str = parsed.get("strengths")
        if isinstance(p_str, list) and p_str:
            strengths = [str(x) for x in p_str][:6]
        p_gaps = parsed.get("gaps")
        if isinstance(p_gaps, list) and p_gaps:
            gray_areas = [
                str(g.get("text") if isinstance(g, dict) else g).strip()
                for g in p_gaps
            ]
            gray_areas = [g for g in gray_areas if g][:8]
        verdict_hint = str(parsed.get("verdict") or "").lower()

    ai_scores = [s["ai_score"] for s in sections]
    overall = round(sum(ai_scores) / len(ai_scores))
    verdict = verdict_hint if verdict_hint in ("verified", "partial", "gray") else _verdict_for(overall)
    return {
        "sections": sections,
        "overall_score": overall,
        "verdict": verdict,
        "strengths": strengths,
        "gray_areas": gray_areas,
        "candidate": candidate,
        "skill": skill,
    }


async def build_report_from_transcript(
    db: AsyncSession, row: AssessmentTranscript
) -> Optional[SessionReport]:
    """Create/upsert the SME's pending report + draft session report from a
    just-ingested transcript. Returns None (no report) for untraceable rooms
    — an ad-hoc session with no candidate isn't a reviewable assessment."""
    if not row.candidate_user_id:
        return None

    gen = await generate_report_from_transcript(db, row)
    if gen is None:
        # Nothing the candidate actually answered — no report to review yet.
        return None

    sections = gen["sections"]
    candidate = gen["candidate"]
    skill = gen["skill"]
    overall = gen["overall_score"]
    verdict = gen["verdict"]
    strengths = gen["strengths"]
    gray_areas = gen["gray_areas"]
    now = datetime.now(timezone.utc)
    # Short, real date label for the queue row (what the seed rows use).
    date_label = now.strftime("%b %d, %Y")

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
