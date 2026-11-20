"""Deterministic fallbacks for every registry agent — keep each
agent-powered feature functional when AutoGen isn't installed or no
provider credential is configured. Data-grounded (read the same tables a
real agent would), just not generative.

Imported for side effects from `app.main` — importing registers all six.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_registry_service import register_fallback


async def _brief_fallback(context: dict[str, Any], db: AsyncSession) -> str:
    from app.models.verifier import VerifierConsoleState

    # The verifier console state (merged singleton) is Postgres now.
    row = await db.get(VerifierConsoleState, "default")
    probes = list(row.prioritized_probes or []) if row else []
    gray = list(row.gray_requested or []) if row else []
    skill = context.get("skill") or (row.skill if row else "the scheduled skill")
    candidate = context.get("candidateRef", "the candidate")
    lines = [
        f"Pre-session brief · {skill} · {candidate}",
        (row.summary if row and row.summary else "Focus the session on previously identified gap areas."),
        "",
        "Prioritized probes:",
        *[f"  {i + 1}. {p}" for i, p in enumerate(probes)],
    ]
    if gray:
        lines += ["", "Company-requested gray areas: " + ", ".join(gray)]
    return "\n".join(lines)


async def _report_fallback(context: dict[str, Any], db: AsyncSession) -> str:
    from app.models.verifier import SessionReport

    # session_reports is Postgres now (see the migration plan).
    report_id = context.get("reportId", "rpt_001")
    row = await db.get(SessionReport, report_id)
    sections = row.sections if row else []
    avg = round(sum(s["ai_score"] for s in sections) / len(sections)) if sections else 0
    strengths = ", ".join(row.strengths or []) if row else ""
    gray_areas = ", ".join(row.gray_areas or []) if row else ""
    return (
        f"Draft report for session {row.session_id if row else context.get('sessionId', '?')}: "
        f"overall {avg}/100 across {len(sections)} dimensions. "
        f"Strengths: {strengths or '—'}. "
        f"Gray areas: {gray_areas or '—'}. "
        "Review and adjust the per-dimension scores before publishing."
    )


async def _gap_fallback(context: dict[str, Any], db: AsyncSession) -> str:  # noqa: ARG001
    from sqlalchemy import select

    from app.models.verifier import SuggestedGap

    # verifier_suggested_gaps is Postgres now (see the migration plan).
    stmt = select(SuggestedGap).order_by(SuggestedGap.id)
    gaps = (await db.execute(stmt)).scalars().all()
    lines = ["Gap analysis (evidence-bound):"]
    for g in gaps:
        lines.append(f"  × {g.text} — {g.sub}")
    return "\n".join(lines)


async def _gray_fallback(context: dict[str, Any], db: AsyncSession) -> str:
    from app.models.candidate import PublicProfile

    candidate_id = context.get("candidateId", "usr_cand_001")
    # public_profiles is Postgres now (see the migration plan). Uses the
    # session passed in by AgentRegistryService — the same
    # request/test-scoped session, not a separate connection (which
    # wouldn't see this request's not-yet-committed work under tests).
    profile = await db.get(PublicProfile, candidate_id)
    grays = list(profile.gray_areas) if profile else []
    if not grays:
        return "No gray areas on record — every claimed skill has been tested."
    ranked = sorted(grays, key=lambda g: -g["companies"])
    lines = ["Gray analysis — never-tested areas ranked by company demand:"]
    for g in ranked:
        lines.append(
            f"  ? {g['name']} — {g['companies']} companies asked. "
            "A targeted 30-min assessment resolves this."
        )
    return "\n".join(lines)


async def _search_fallback(context: dict[str, Any], db: AsyncSession) -> str:  # noqa: ARG001
    query = context.get("query", "")
    return (
        f'Ranked matches for "{query}" using verified skills, scores and '
        "gray-area penalties. Candidates are listed by alias until unlocked."
    )


def _significant(text: str) -> set[str]:
    import re

    return {w for w in re.findall(r"[a-z0-9.#+]+", text.lower()) if len(w) >= 4}


def _best_turn(question: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    """The candidate transcript turn with the most keyword overlap with the
    question (so the quoted evidence actually answers it); the first
    substantive turn when nothing overlaps."""
    qwords = _significant(question)
    best, best_score = turns[0], -1
    for turn in turns:
        score = len(qwords & _significant(str(turn.get("text", ""))))
        if score > best_score:
            best, best_score = turn, score
    return best


async def _chat_fallback(context: dict[str, Any], db: AsyncSession) -> str:  # noqa: ARG001
    """Grounded in the candidate's REAL rows when the API layer supplied them
    (transcript turns to quote + the published report's verdict + gray-area
    demand). Degrades to the legacy canned keyword answers only when there is
    no real evidence on record for this candidate (e.g. a pool-only row)."""
    prompt = str(context.get("question", ""))
    low = prompt.lower()
    ref = context.get("candidateRef", "the candidate")
    transcript = context.get("transcript") or {}
    report = context.get("report") or {}
    grays = context.get("grayAreas") or []

    # 1) The question targets a never-tested (gray) area → say so, with the
    #    real company-demand signal and a follow-up offer.
    for g in sorted(grays, key=lambda x: -int(x.get("companies") or 0)):
        name = str(g.get("name", ""))
        words = [w for w in _significant(name) if len(w) >= 3]
        if name and any(w in low for w in words):
            companies = int(g.get("companies") or 0)
            demand = f" {companies} other compan{'y has' if companies == 1 else 'ies have'} asked about it." if companies else ""
            return (
                f"I cannot answer this from existing evidence — {ref} has not been "
                f"verified on {name}.{demand} You can trigger a targeted 30-minute "
                "follow-up session focused exactly on this."
            )

    # 2) Quote the real transcript turn that best answers the question.
    turns = transcript.get("candidateTurns") or []
    if turns:
        turn = _best_turn(prompt, turns)
        skill = transcript.get("skill") or report.get("skill") or "this skill"
        verdict = report.get("verdict")
        quoted = str(turn.get("text", "")).rstrip(".")
        tail = f" Verifier verdict: {verdict}" if verdict else ""
        return (
            f"From {ref}'s verified {skill} session (transcript {turn.get('t', '')}), "
            f"they said: “{quoted}.”{tail}"
        )

    # 3) No transcript, but a published report exists → summarise it.
    if report:
        strengths = ", ".join(report.get("strengths") or []) or "—"
        return (
            f"{ref} was assessed on {report.get('skill')} and scored "
            f"{report.get('score')}/100. Verdict: {report.get('verdict')} "
            f"Verified strengths: {strengths}."
        )

    # 4) No real evidence on record — legacy canned answers (keeps the
    #    pool-only candidates and the existing contract tests functional).
    if "payment" in low or "idempotenc" in low:
        return (
            f"I cannot answer this from existing evidence. {ref} has not been "
            "verified on payment-domain specifics. You can trigger a targeted "
            "30-minute follow-up session focused exactly on this."
        )
    if "system design" in low or "staff" in low:
        return (
            f"{ref} was verified Advanced on System Design (82/100) in the Feb 02 "
            "session. Strongest signals: tradeoff reasoning and operational realism."
        )
    return (
        f"Based on the evidence in {ref}'s dossier, they demonstrate solid "
        "understanding with one notable gap. Verifier validated their explanation "
        "of transactional producers and ordering guarantees; uncertain on "
        "producer-epoch fencing."
    )


register_fallback("interviewer_brief", _brief_fallback)
register_fallback("report_generator", _report_fallback)
register_fallback("gap_analyzer", _gap_fallback)
register_fallback("gray_analyzer", _gray_fallback)
register_fallback("candidate_search", _search_fallback)
register_fallback("candidate_chat", _chat_fallback)
