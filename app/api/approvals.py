"""HTTP layer for interviewer approvals + specialist invites.

Admin endpoints mirror `handlers/approvals.ts`; the candidate
self-request endpoint lives under /api/candidate.
"""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal, get_current_principal, require_roles
from app.db.session import get_session
from app.schemas.approvals import (
    ApprovalsOverview,
    DecisionBody,
    InterviewerApproval,
    SelfRequestBody,
    SpecialistInvite,
    SpecialistInviteBody,
)
from app.services.approvals_service import ApprovalsService

admin_router = APIRouter(
    tags=["Admin · Interviewer Approvals"],
    dependencies=[Depends(require_roles("admin"))],
)
candidate_router = APIRouter(tags=["Candidate · Interviewer Request"])


def _service(db: AsyncSession = Depends(get_session)) -> ApprovalsService:
    return ApprovalsService(db)


@admin_router.get("", response_model=ApprovalsOverview)
async def overview(service: ApprovalsService = Depends(_service)) -> ApprovalsOverview:
    return await service.overview()


@admin_router.post("/{approval_id}/approve", response_model=InterviewerApproval)
async def approve(
    approval_id: str,
    body: DecisionBody = Body(default_factory=DecisionBody),
    principal: Principal = Depends(require_roles("admin")),
    service: ApprovalsService = Depends(_service),
) -> InterviewerApproval:
    return await service.approve(approval_id, principal.actor_id, body.note)


@admin_router.post("/{approval_id}/reject", response_model=InterviewerApproval)
async def reject(
    approval_id: str,
    body: DecisionBody = Body(default_factory=DecisionBody),
    principal: Principal = Depends(require_roles("admin")),
    service: ApprovalsService = Depends(_service),
) -> InterviewerApproval:
    return await service.reject(approval_id, principal.actor_id, body.note)


@candidate_router.post(
    "/interviewer-request",
    response_model=InterviewerApproval,
    status_code=201,
)
async def self_request(
    body: SelfRequestBody,
    principal: Principal = Depends(get_current_principal),
    service: ApprovalsService = Depends(_service),
) -> InterviewerApproval:
    return await service.self_request(body, principal.user_doc)


specialists_router = APIRouter(
    tags=["Admin · Specialist Invites"],
    dependencies=[Depends(require_roles("admin"))],
)


@specialists_router.post("/invite", response_model=SpecialistInvite, status_code=201)
async def invite_specialist(
    body: SpecialistInviteBody,
    principal: Principal = Depends(require_roles("admin")),
    service: ApprovalsService = Depends(_service),
) -> SpecialistInvite:
    return await service.invite_specialist(body, principal.actor_id)
