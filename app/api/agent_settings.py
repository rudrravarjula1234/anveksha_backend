"""HTTP layer for the agent registry + agent-powered feature endpoints.

Admin settings (model binding + system message, per agent):
    GET    /api/admin/agents
    PATCH  /api/admin/agents/{agent_id}
    POST   /api/admin/agents/{agent_id}/reset

Feature executions (each resolves through the registry — real agent when
framework + credentials exist, deterministic fallback otherwise):
    POST /api/verifier/sessions/{session_id}/brief      (interviewer)
    POST /api/verifier/reports/{report_id}/generate     (interviewer)
    POST /api/agents/gray-analysis                      (any authenticated)
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal, get_current_principal, require_roles
from app.db.session import get_session
from app.schemas.agent_registry import AgentConfig, AgentConfigPatch, AgentRunResult
from app.services.agent_registry_service import AgentRegistryService

admin_router = APIRouter(
    tags=["Admin · Agents"],
    dependencies=[Depends(require_roles("admin"))],
)
verifier_router = APIRouter(
    tags=["Verifier · Agent features"],
    dependencies=[Depends(require_roles("interviewer", "admin"))],
)
shared_router = APIRouter(
    tags=["Agents · Shared"],
    dependencies=[Depends(get_current_principal)],
)


def _service(db: AsyncSession = Depends(get_session)) -> AgentRegistryService:
    return AgentRegistryService(db)


# ─── Admin settings ──────────────────────────────────────────────────────

@admin_router.get("", response_model=list[AgentConfig])
async def list_agents(service: AgentRegistryService = Depends(_service)) -> list[AgentConfig]:
    return await service.list_agents()


@admin_router.patch("/{agent_id}", response_model=AgentConfig)
async def patch_agent(
    agent_id: str,
    patch: AgentConfigPatch,
    principal: Principal = Depends(require_roles("admin")),
    service: AgentRegistryService = Depends(_service),
) -> AgentConfig:
    return await service.patch(agent_id, patch, principal.actor_id)


@admin_router.post("/{agent_id}/reset", response_model=AgentConfig)
async def reset_agent(
    agent_id: str,
    principal: Principal = Depends(require_roles("admin")),
    service: AgentRegistryService = Depends(_service),
) -> AgentConfig:
    return await service.reset_system_message(agent_id, principal.actor_id)


# ─── Feature executions ──────────────────────────────────────────────────

@verifier_router.post("/sessions/{session_id}/brief", response_model=AgentRunResult)
async def generate_brief(
    session_id: str,
    body: Optional[dict[str, Any]] = Body(default=None),
    service: AgentRegistryService = Depends(_service),
) -> AgentRunResult:
    """On-demand pre-session brief — the interviewer opts in per session.

    The brief is NOT pre-generated; this call assembles the context and
    runs the `interviewer_brief` agent at click time.
    """
    context = {
        "task": "Generate the pre-session brief for this scheduled interview.",
        "sessionId": session_id,
        **(body or {}),
    }
    return await service.run_agent("interviewer_brief", context)


@verifier_router.post("/reports/{report_id}/generate", response_model=AgentRunResult)
async def generate_report(
    report_id: str,
    service: AgentRegistryService = Depends(_service),
) -> AgentRunResult:
    """Agent-drafted report + gap analysis for a completed session."""
    return await service.run_agent(
        "report_generator",
        {"task": "Draft the structured skill report for this session.", "reportId": report_id},
    )


@shared_router.post("/gray-analysis", response_model=AgentRunResult)
async def gray_analysis(
    body: dict[str, Any] = Body(default_factory=dict),
    service: AgentRegistryService = Depends(_service),
) -> AgentRunResult:
    """Gray analysis — available on candidate, company and admin surfaces."""
    return await service.run_agent(
        "gray_analyzer",
        {"task": "Identify and rank never-tested (gray) areas.", **body},
    )


@shared_router.post("/gap-analysis", response_model=AgentRunResult)
async def gap_analysis(
    body: dict[str, Any] = Body(default_factory=dict),
    service: AgentRegistryService = Depends(_service),
) -> AgentRunResult:
    """Gap analysis — tested-and-weak areas with transcript citations. Used by
    the verifier report editor and the candidate skill-report detail page."""
    return await service.run_agent(
        "gap_analyzer",
        {"task": "Identify tested-and-weak gap areas, each grounded in evidence.", **body},
    )


@shared_router.post("/candidate-search", response_model=AgentRunResult)
async def candidate_search(
    body: dict[str, Any] = Body(default_factory=dict),
    service: AgentRegistryService = Depends(_service),
) -> AgentRunResult:
    """Natural-language candidate ranking for company discovery. Privacy-aware:
    the agent presents aliases until a candidate is unlocked."""
    return await service.run_agent(
        "candidate_search",
        {"task": "Rank the verified pool against this hiring need.", **body},
    )
