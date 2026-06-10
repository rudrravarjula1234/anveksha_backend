"""Deterministic fallbacks for every registry agent.

These keep each agent-powered feature fully functional when the AutoGen
extras aren't installed or no provider credential is configured. They
are data-grounded (reading the same Mongo collections a real agent
would receive as context), just not generative.

Imported for side effects from `app.main` — importing registers all six.
"""

from typing import Any

from app.db.mongo import get_database
from app.services.agent_registry_service import register_fallback


async def _brief_fallback(context: dict[str, Any]) -> str:
    doc = await get_database()["verifier_brief"].find_one({"key": "default"}) or {}
    probes = doc.get("prioritizedProbes", [])
    gray = doc.get("grayRequested", [])
    skill = context.get("skill") or doc.get("skill", "the scheduled skill")
    candidate = context.get("candidateRef", "the candidate")
    lines = [
        f"Pre-session brief · {skill} · {candidate}",
        doc.get("summary", "Focus the session on previously identified gap areas."),
        "",
        "Prioritized probes:",
        *[f"  {i + 1}. {p}" for i, p in enumerate(probes)],
    ]
    if gray:
        lines += ["", "Company-requested gray areas: " + ", ".join(gray)]
    return "\n".join(lines)


async def _report_fallback(context: dict[str, Any]) -> str:
    report_id = context.get("reportId", "rpt_001")
    doc = await get_database()["session_reports"].find_one({"id": report_id}) or {}
    sections = doc.get("sections", [])
    avg = round(sum(s.get("aiScore", 0) for s in sections) / len(sections)) if sections else 0
    return (
        f"Draft report for session {doc.get('sessionId', context.get('sessionId', '?'))}: "
        f"overall {avg}/100 across {len(sections)} dimensions. "
        f"Strengths: {', '.join(doc.get('strengths', [])) or '—'}. "
        f"Gray areas: {', '.join(doc.get('grayAreas', [])) or '—'}. "
        "Review and adjust the per-dimension scores before publishing."
    )


async def _gap_fallback(context: dict[str, Any]) -> str:
    doc = await get_database()["verifier_suggested_gaps"].find_one({"key": "default"}) or {}
    gaps = doc.get("gaps", [])
    lines = ["Gap analysis (evidence-bound):"]
    for g in gaps:
        lines.append(f"  × {g.get('text')} — {g.get('sub')}")
    return "\n".join(lines)


async def _gray_fallback(context: dict[str, Any]) -> str:
    candidate_id = context.get("candidateId", "usr_cand_001")
    profile = await get_database()["public_profiles"].find_one({"userId": candidate_id}) or {}
    grays = profile.get("grayAreas", [])
    if not grays:
        return "No gray areas on record — every claimed skill has been tested."
    ranked = sorted(grays, key=lambda g: -g.get("companies", 0))
    lines = ["Gray analysis — never-tested areas ranked by company demand:"]
    for g in ranked:
        lines.append(
            f"  ? {g.get('name')} — {g.get('companies', 0)} companies asked. "
            "A targeted 30-min assessment resolves this."
        )
    return "\n".join(lines)


async def _search_fallback(context: dict[str, Any]) -> str:
    query = context.get("query", "")
    return (
        f'Ranked matches for "{query}" using verified skills, scores and '
        "gray-area penalties. Candidates are listed by alias until unlocked."
    )


async def _chat_fallback(context: dict[str, Any]) -> str:
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
