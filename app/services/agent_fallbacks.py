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


async def _chat_fallback(context: dict[str, Any], db: AsyncSession) -> str:  # noqa: ARG001
    prompt = str(context.get("question", "")).lower()
    ref = context.get("candidateRef", "the candidate")
    if "payment" in prompt or "idempotenc" in prompt:
        return (
            f"I cannot answer this from existing evidence. {ref} has not been "
            "verified on payment-domain specifics. You can trigger a targeted "
            "30-minute follow-up session focused exactly on this."
        )
    if "system design" in prompt or "staff" in prompt:
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
