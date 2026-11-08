"""Pre-defined agent registry seed.

Six agents ship with the platform. Admins can re-point the model and
edit the system message per agent (stored here in Postgres);
`defaultSystemMessage` is kept immutable so a reset is always possible.
"""

from sqlalchemy.ext.asyncio import AsyncSession

_BRIEF_SM = (
    "You are Anveksha's interview-brief agent. Given a scheduled verification "
    "session (candidate's claimed skill, prior session reports, gap areas, and "
    "company-requested gray areas), produce a concise pre-session brief for the "
    "interviewer: 1) what to skip, 2) three prioritized probes targeting known "
    "gaps, 3) gray areas companies asked about. NEVER include the candidate's "
    "name or personal details — refer to them only by their candidate ID. "
    "Keep it under 150 words."
)

_REPORT_SM = (
    "You are Anveksha's report-generation agent. Given a completed session "
    "transcript with timestamps, produce a structured skill report: per-dimension "
    "rubric scores (0-100), a one-line verdict, a longer verdict paragraph, "
    "summary items (demonstrated), gap items (tested and weak, each grounded in a "
    "transcript timestamp), and evidence excerpts. Be evidence-bound: never infer "
    "skills that weren't probed. Output JSON matching the SessionReport schema."
)

_GAP_SM = (
    "You are Anveksha's gap-analysis agent. Given session evidence for a "
    "candidate, identify GAP areas: topics that were explicitly tested where the "
    "answer was incomplete, hesitant, or wrong. Each gap must cite the transcript "
    "moment. Classify severity (low/medium/high). Do not list topics that were "
    "never probed — those are GRAY, not gaps."
)

_GRAY_SM = (
    "You are Anveksha's gray-analysis agent. Given a candidate's verified skill "
    "ledger and the set of topics companies have asked about, identify GRAY "
    "areas: topics never tested in any session. A gray is neither pass nor fail — "
    "it is an open question. Rank by how many companies asked. Suggest the "
    "targeted follow-up assessment that would resolve each."
)

_SEARCH_SM = (
    "You are Anveksha's candidate-search agent. Given a natural-language hiring "
    "need, rank candidates from the verified-talent pool by fit. Score matches "
    "using verified skills (high weight), verification scores, recency, and gray "
    "areas (penalty when the need hits an untested area). Respect privacy: "
    "candidates are presented by alias until the company unlocks them — never "
    "reveal names, emails, or exact locations for locked candidates."
)

_CHAT_SM = (
    "You are Anveksha's candidate-investigation agent. Companies ask questions "
    "about a specific candidate; you answer ONLY from verified session evidence "
    "(transcripts, reports, rubric scores). If the question touches an area never "
    "tested, say you cannot answer from evidence and offer a targeted follow-up "
    "assessment. Cite transcript timestamps. 2-4 sentences. Never speculate. "
    "Never reveal personal details of locked candidates."
)

AGENT_SEEDS: list[dict] = [
    {
        "id": "interviewer_brief",
        "name": "Interview Brief",
        "description": "On-demand pre-session brief for interviewers: what to skip, prioritized probes, requested gray areas.",
        "usedBy": ["Verifier · scheduled interview → Generate brief"],
        "modelId": None,
        "systemMessage": _BRIEF_SM,
        "defaultSystemMessage": _BRIEF_SM,
        "temperature": 0.3,
        "enabled": True,
    },
    {
        "id": "report_generator",
        "name": "Report Generator",
        "description": "Drafts the structured skill report from a completed session transcript.",
        "usedBy": ["Verifier · session completion", "Verifier · pending reports"],
        "modelId": None,
        "systemMessage": _REPORT_SM,
        "defaultSystemMessage": _REPORT_SM,
        "temperature": 0.2,
        "enabled": True,
    },
    {
        "id": "gap_analyzer",
        "name": "Gap Analyzer",
        "description": "Identifies tested-and-weak areas with transcript citations and severity.",
        "usedBy": ["Verifier · report editor", "Candidate · skill report detail"],
        "modelId": None,
        "systemMessage": _GAP_SM,
        "defaultSystemMessage": _GAP_SM,
        "temperature": 0.2,
        "enabled": True,
    },
    {
        "id": "gray_analyzer",
        "name": "Gray Analyzer",
        "description": "Identifies never-tested areas across all surfaces and ranks them by company demand.",
        "usedBy": ["Candidate · insights", "Company · gray follow-ups", "Public profile"],
        "modelId": None,
        "systemMessage": _GRAY_SM,
        "defaultSystemMessage": _GRAY_SM,
        "temperature": 0.3,
        "enabled": True,
    },
    {
        "id": "candidate_search",
        "name": "Candidate Search",
        "description": "Ranks the verified pool against a natural-language hiring need. Privacy-aware (aliases until unlock).",
        "usedBy": ["Company · discovery"],
        "modelId": None,
        "systemMessage": _SEARCH_SM,
        "defaultSystemMessage": _SEARCH_SM,
        "temperature": 0.4,
        "enabled": True,
    },
    {
        "id": "candidate_chat",
        "name": "Candidate Chat",
        "description": "Evidence-grounded Q&A about a specific candidate for companies.",
        "usedBy": ["Company · AI investigate"],
        "modelId": None,
        "systemMessage": _CHAT_SM,
        "defaultSystemMessage": _CHAT_SM,
        "temperature": 0.4,
        "enabled": True,
    },
]


async def seed_agent_registry(db: AsyncSession) -> int:
    from app.models.agent_registry import AgentConfig
    from app.repositories.agent_registry_repo import AgentRegistryRepository

    repo = AgentRegistryRepository(db)
    inserted = 0
    for template in AGENT_SEEDS:
        if await repo.find_by_id(template["id"]):
            continue
        db.add(
            AgentConfig(
                id=template["id"],
                name=template["name"],
                description=template["description"],
                used_by=template["usedBy"],
                model_id=template["modelId"],
                system_message=template["systemMessage"],
                default_system_message=template["defaultSystemMessage"],
                temperature=template["temperature"],
                enabled=template["enabled"],
            )
        )
        inserted += 1
    if inserted:
        await db.flush()
    return inserted
