"""HTTP layer for the company portal.

Spans several prefixes (mounted at /api in main.py):
  /companies/me, /companies/me/interviewers, /companies/me/credits
  /companies/pipeline, /companies/followup, /companies/chat
  /company/team, /company/billing, /company/gray-followups
  /ai-search
  /admin/credit-rate (admin-only)
"""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal, get_current_principal, require_roles
from app.db.session import get_session
from app.schemas.company import (
    AnonymousInterviewer,
    AnonymousInterviewerCreate,
    BillingResponse,
    ChatRequest,
    CompanyCredits,
    CompanyProfile,
    CreditMutation,
    CreditRate,
    CreditRatePatch,
    FollowupRequest,
    FollowupSkillOption,
    FollowupTracking,
    GrayDemandItem,
    PipelineBoard,
    PipelineMove,
    SearchRequest,
    SearchResponse,
    TeamInvite,
    TeamMember,
)
from app.services.company_service import CompanyService

router = APIRouter(
    tags=["Company"],
    dependencies=[Depends(get_current_principal)],
)
admin_router = APIRouter(
    tags=["Admin · Credit Rate"],
    dependencies=[Depends(require_roles("admin"))],
)


def _service(db: AsyncSession = Depends(get_session)) -> CompanyService:
    return CompanyService(db)


# ─── Company + anonymous interviewers ────────────────────────────────────

@router.get("/companies/me", response_model=CompanyProfile)
async def company_me(service: CompanyService = Depends(_service)) -> CompanyProfile:
    return await service.company()


@router.get("/companies/me/interviewers", response_model=list[AnonymousInterviewer])
async def list_interviewers(service: CompanyService = Depends(_service)) -> list[AnonymousInterviewer]:
    return await service.interviewers()


@router.post("/companies/me/interviewers", response_model=AnonymousInterviewer, status_code=201)
async def add_interviewer(
    body: AnonymousInterviewerCreate,
    service: CompanyService = Depends(_service),
) -> AnonymousInterviewer:
    return await service.add_interviewer(body)


@router.post("/companies/me/interviewers/{interviewer_id}/verify-email", response_model=AnonymousInterviewer)
async def verify_interviewer(
    interviewer_id: str,
    service: CompanyService = Depends(_service),
) -> AnonymousInterviewer:
    return await service.verify_interviewer(interviewer_id)


@router.delete("/companies/me/interviewers/{interviewer_id}")
async def remove_interviewer(
    interviewer_id: str,
    service: CompanyService = Depends(_service),
) -> dict[str, bool]:
    await service.remove_interviewer(interviewer_id)
    return {"ok": True}


# ─── Credits ─────────────────────────────────────────────────────────────

@router.get("/companies/me/credits", response_model=CompanyCredits)
async def credits(service: CompanyService = Depends(_service)) -> CompanyCredits:
    return await service.credits()


@router.post("/companies/me/credits/earn", response_model=CompanyCredits)
async def earn(body: CreditMutation, service: CompanyService = Depends(_service)) -> CompanyCredits:
    return await service.earn(body)


@router.post("/companies/me/credits/spend", response_model=CompanyCredits)
async def spend(body: CreditMutation, service: CompanyService = Depends(_service)) -> CompanyCredits:
    return await service.spend(body)


@admin_router.get("", response_model=CreditRate)
async def get_credit_rate(service: CompanyService = Depends(_service)) -> CreditRate:
    return await service.credit_rate()


@admin_router.patch("", response_model=CreditRate)
async def set_credit_rate(
    body: CreditRatePatch,
    principal: Principal = Depends(require_roles("admin")),
    service: CompanyService = Depends(_service),
) -> CreditRate:
    return await service.set_credit_rate(body.rupeesPerCredit, principal.actor_id)


# ─── Team + billing ──────────────────────────────────────────────────────

@router.get("/company/team", response_model=list[TeamMember])
async def team(service: CompanyService = Depends(_service)) -> list[TeamMember]:
    return await service.team()


@router.post("/company/team", response_model=TeamMember, status_code=201)
async def invite_member(body: TeamInvite, service: CompanyService = Depends(_service)) -> TeamMember:
    return await service.invite_member(body)


@router.delete("/company/team/{member_id}")
async def remove_member(member_id: str, service: CompanyService = Depends(_service)) -> dict[str, bool]:
    await service.remove_member(member_id)
    return {"ok": True}


@router.get("/company/billing", response_model=BillingResponse)
async def billing(service: CompanyService = Depends(_service)) -> BillingResponse:
    return await service.billing()


# ─── Gray follow-ups ─────────────────────────────────────────────────────

@router.get("/company/gray-followups", response_model=list[FollowupTracking])
async def gray_followups(service: CompanyService = Depends(_service)) -> list[FollowupTracking]:
    return await service.gray_followups()


@router.post("/company/gray-followups/{followup_id}/remind")
async def remind_followup(followup_id: str, service: CompanyService = Depends(_service)) -> dict[str, Any]:
    return await service.remind_followup(followup_id)


@router.delete("/company/gray-followups/{followup_id}")
async def delete_followup(followup_id: str, service: CompanyService = Depends(_service)) -> dict[str, bool]:
    await service.delete_followup(followup_id)
    return {"ok": True}


# ─── Discovery / pipeline / follow-up requests / chat ────────────────────

@router.post("/ai-search", response_model=SearchResponse)
async def ai_search(body: SearchRequest, service: CompanyService = Depends(_service)) -> SearchResponse:
    return await service.search(body)


@router.post("/companies/candidates/{candidate_id}/unlock")
async def unlock_candidate(
    candidate_id: str,
    service: CompanyService = Depends(_service),
) -> dict[str, Any]:
    """Reveal a candidate's identity. Costs credits (402 when short)."""
    return await service.unlock_candidate(candidate_id)


@router.get("/companies/candidates/{candidate_id}/gray-demand", response_model=list[GrayDemandItem])
async def gray_demand(
    candidate_id: str,
    service: CompanyService = Depends(_service),
) -> list[GrayDemandItem]:
    """The candidate's real never-tested areas ranked by company demand —
    drives the dossier page's gray-demand panel (grows as the chat probes
    those areas)."""
    rows = await service.gray_demand(candidate_id)
    return [GrayDemandItem(name=g["name"], companies=int(g.get("companies") or 0)) for g in rows]


@router.get("/companies/pipeline", response_model=PipelineBoard)
async def pipeline(service: CompanyService = Depends(_service)) -> PipelineBoard:
    return await service.pipeline()


@router.post("/companies/pipeline/{candidate_id}/move")
async def move_pipeline(
    candidate_id: str,
    body: PipelineMove,
    service: CompanyService = Depends(_service),
) -> dict[str, Any]:
    return await service.move_pipeline(candidate_id, body.stage)


@router.get("/companies/followup/skills", response_model=list[FollowupSkillOption])
async def followup_skills(service: CompanyService = Depends(_service)) -> list[FollowupSkillOption]:
    return await service.followup_skills()


@router.post("/companies/followup")
async def request_followup(
    body: FollowupRequest,
    service: CompanyService = Depends(_service),
) -> dict[str, Any]:
    return await service.request_followup(body.candidateId, body.skills, body.message)


@router.post("/companies/chat")
async def chat(
    body: ChatRequest,
    service: CompanyService = Depends(_service),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Streamed plain-text answer with a typing cadence.

    Runs the `candidate_chat` registry agent when the framework +
    credentials are configured; otherwise streams the deterministic
    fallback. Locked candidates are referred to by alias only.
    """
    from app.core.privacy import candidate_alias  # noqa: PLC0415
    from app.services.agent_registry_service import AgentRegistryService  # noqa: PLC0415

    locked = not (body.candidateId and await service.is_unlocked(body.candidateId))
    if locked:
        ref = candidate_alias(body.candidateId)
    else:
        # Address an unlocked candidate by their real name, not their id.
        ref = await service.candidate_display_name(body.candidateId) or body.candidateId

    # Context is built from the candidate's REAL rows (transcript turns,
    # published report, gray-area demand) — see CompanyService.build_chat_context.
    context = await service.build_chat_context(
        body.candidateId, body.prompt, locked=locked, ref=ref
    )
    # A question that targets a known gray area bumps its demand counter so
    # the dossier's gray panel reflects the fresh signal on reload.
    await service.note_gray_interest(body.candidateId, body.prompt)

    registry = AgentRegistryService(db)
    result = await registry.run_agent("candidate_chat", context)
    answer = result.output
    if locked:
        # Belt-and-braces: scrub the seeded candidate's name from canned text.
        answer = answer.replace("Aarav", ref).replace("’s’", "'s")

    # Perf (H4): the typing cadence used to sleep 40 ms per 24-char chunk
    # unconditionally — every answer paid ~40 ms × ceil(len/24) of pure
    # artificial delay (chat's p50 was ~480 ms, almost all of it sleep).
    # Keep the cadence feel but bound its TOTAL cost: chunks stream for at
    # most ~120 ms, then the remainder arrives immediately. The reassembled
    # response body is byte-identical either way.
    async def _gen():
        spent = 0.0
        for i in range(0, len(answer), 24):
            yield answer[i : i + 24]
            if spent < 0.12:
                step = min(0.04, 0.12 - spent)
                await asyncio.sleep(step)
                spent += step

    return StreamingResponse(_gen(), media_type="text/plain; charset=utf-8")
