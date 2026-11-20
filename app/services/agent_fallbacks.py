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


# ─── Candidate chat (evidence-only) ─────────────────────────────────────
#
# Only used when no model answers. It doesn't try to interpret the question;
# it states what is on file — the candidate's skill ledger and report gaps,
# exactly as the chat endpoint passes them in.

_STATE_LABELS = (
    ("verified", "Verified"),
    ("partial", "Partially verified"),
    ("gray", "Untested"),
    ("claimed", "Claimed but not verified"),
)


async def _chat_fallback(context: dict[str, Any], db: AsyncSession) -> str:  # noqa: ARG001
    name = str(context.get("candidateRef") or "This candidate")
    skills: list[dict[str, Any]] = (context.get("evidence") or {}).get("skills") or []
    if not skills:
        return f"There is no verified session evidence for {name} yet."

    def listing(state: str) -> str:
        return ", ".join(
            f"{s['name']} ({s['score']})" if s.get("score") is not None else s["name"]
            for s in skills if s["state"] == state
        )

    facts = ". ".join(f"{label}: {v}" for state, label in _STATE_LABELS if (v := listing(state)))
    gaps = " · ".join(f"{s['name']}: {'; '.join(s['gaps'][:2])}" for s in skills if s.get("gaps"))
    return (
        f"The AI assistant is unavailable right now, so here is what's on file for {name}. {facts}."
        + (f" Gaps found in sessions — {gaps}." if gaps else "")
    )


register_fallback("interviewer_brief", _brief_fallback)
register_fallback("report_generator", _report_fallback)
register_fallback("gap_analyzer", _gap_fallback)
register_fallback("gray_analyzer", _gray_fallback)
register_fallback("candidate_search", _search_fallback)
register_fallback("candidate_chat", _chat_fallback)
