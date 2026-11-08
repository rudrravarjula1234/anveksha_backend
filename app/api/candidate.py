"""HTTP layer for `/api/candidate`, `/api/notifications` and `/api/profiles/me`.

Contract mirror of the candidate-extras handlers in `adminRich.ts` and
`profiles.ts`. Any authenticated user can read these — interviewer
personas are candidates too in the dual-role model.
"""

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.candidate import (
    AppNotification,
    CandidateInsight,
    OnboardingStep,
    PublicProfileData,
    SessionHistoryRow,
    SkillReport,
    SkillReportDetail,
    UserProfileMe,
    UserProfilePatch,
)
from app.services.candidate_service import CandidateService

router = APIRouter(
    tags=["Candidate"],
    dependencies=[Depends(get_current_principal)],
)


def _service(db: AsyncSession = Depends(get_session)) -> CandidateService:
    return CandidateService(db)


# ─── Skill reports ───────────────────────────────────────────────────────

@router.get("/candidate/skill-reports", response_model=list[SkillReport])
async def skill_reports(
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> list[SkillReport]:
    return await service.skill_reports(principal.user_id)


@router.get("/candidate/skill-reports/{report_id}", response_model=SkillReportDetail)
async def skill_report_detail(
    report_id: str,
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> SkillReportDetail:
    return await service.skill_report_detail(principal.user_id, report_id)


# ─── Insights ────────────────────────────────────────────────────────────

@router.get("/candidate/insights", response_model=list[CandidateInsight])
async def insights(
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> list[CandidateInsight]:
    return await service.insights(principal.user_id)


@router.post("/candidate/insights/{insight_id}/act")
async def act_on_insight(
    insight_id: str,
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> dict[str, bool]:
    await service.act_on_insight(principal.user_id, insight_id)
    return {"ok": True}


# ─── Onboarding / public profile / history ───────────────────────────────

@router.get("/candidate/onboarding", response_model=list[OnboardingStep])
async def onboarding(service: CandidateService = Depends(_service)) -> list[OnboardingStep]:
    return await service.onboarding()


@router.get("/candidate/public-profile", response_model=PublicProfileData)
async def public_profile(
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> PublicProfileData:
    return await service.public_profile(principal.user_id)


@router.get("/candidate/session-history", response_model=list[SessionHistoryRow])
async def session_history(
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> list[SessionHistoryRow]:
    return await service.session_history(principal.user_id)


# ─── Notifications ───────────────────────────────────────────────────────

@router.get("/notifications", response_model=list[AppNotification])
async def notifications(
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> list[AppNotification]:
    return await service.notifications(principal.user_id)


@router.post("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: str,
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> dict[str, Any]:
    await service.mark_notification_read(principal.user_id, notification_id)
    return {"ok": True, "id": notification_id}


# ─── /api/profiles/me ────────────────────────────────────────────────────

@router.get("/profiles/me", response_model=UserProfileMe)
async def profile_me(
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> UserProfileMe:
    return await service.profile_me(principal.user_id)


@router.patch("/profiles/me")
async def patch_profile_me(
    patch: UserProfilePatch = Body(default_factory=UserProfilePatch),
    principal: Principal = Depends(get_current_principal),
    service: CandidateService = Depends(_service),
) -> dict[str, Any]:
    # Persists onto the caller's skill_ledgers row (auth required to
    # know whose profile is being edited); response shape unchanged.
    await service.update_profile(principal.user_id, patch)
    return {"ok": True, "patched": patch.model_dump(exclude_unset=True)}
