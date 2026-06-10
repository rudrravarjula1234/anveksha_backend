"""HTTP layer for `/api/verifier` — the interviewer console.

Contract mirror of `anveksha_ui/src/mocks/handlers/verifier.ts` plus the
slots/earnings/profile handlers from `adminRich.ts`. Requires the
interviewer (or admin) role.
"""

from typing import Any

from fastapi import APIRouter, Body, Depends

from app.auth.deps import require_roles
from app.schemas.verifier import (
    GovernanceData,
    NextSessionBrief,
    PendingReportListItem,
    ReportEnvelope,
    VerifierEarnings,
    VerifierProfile,
    VerifierProfileUpdate,
    VerifierQueue,
    VerifierSlot,
    VerifierSlotCreate,
)
from app.services.verifier_service import VerifierService

router = APIRouter(
    tags=["Verifier"],
    dependencies=[Depends(require_roles("interviewer", "admin"))],
)


def _service() -> VerifierService:
    return VerifierService()


@router.get("/queue", response_model=VerifierQueue)
async def queue(service: VerifierService = Depends(_service)) -> VerifierQueue:
    return await service.queue()


@router.get("/next-brief", response_model=NextSessionBrief)
async def next_brief(service: VerifierService = Depends(_service)) -> NextSessionBrief:
    return await service.next_brief()


@router.get("/pending-reports", response_model=list[PendingReportListItem])
async def pending_reports(
    service: VerifierService = Depends(_service),
) -> list[PendingReportListItem]:
    return await service.pending_reports()


@router.get("/reports/{report_id}", response_model=ReportEnvelope)
async def get_report(
    report_id: str,
    service: VerifierService = Depends(_service),
) -> ReportEnvelope:
    return await service.get_report(report_id)


@router.patch("/reports/{report_id}")
async def patch_report(
    report_id: str,
    patch: dict[str, Any] = Body(default_factory=dict),
    service: VerifierService = Depends(_service),
) -> dict[str, Any]:
    return await service.patch_report(report_id, patch)


@router.post("/reports/{report_id}/publish")
async def publish_report(
    report_id: str,
    service: VerifierService = Depends(_service),
) -> dict[str, Any]:
    return await service.publish_report(report_id)


@router.get("/governance", response_model=GovernanceData)
async def governance(service: VerifierService = Depends(_service)) -> GovernanceData:
    return await service.governance()


@router.get("/my-slots", response_model=list[VerifierSlot])
async def my_slots(service: VerifierService = Depends(_service)) -> list[VerifierSlot]:
    return await service.slots()


@router.post("/my-slots", response_model=VerifierSlot)
async def create_slot(
    payload: VerifierSlotCreate,
    service: VerifierService = Depends(_service),
) -> VerifierSlot:
    return await service.create_slot(payload)


@router.delete("/my-slots/{slot_id}")
async def delete_slot(
    slot_id: str,
    service: VerifierService = Depends(_service),
) -> dict[str, bool]:
    await service.delete_slot(slot_id)
    return {"ok": True}


@router.get("/earnings", response_model=VerifierEarnings)
async def earnings(service: VerifierService = Depends(_service)) -> VerifierEarnings:
    return await service.earnings()


@router.get("/my-profile", response_model=VerifierProfile)
async def my_profile(service: VerifierService = Depends(_service)) -> VerifierProfile:
    return await service.profile()


@router.patch("/my-profile", response_model=VerifierProfile)
async def update_my_profile(
    patch: VerifierProfileUpdate,
    service: VerifierService = Depends(_service),
) -> VerifierProfile:
    return await service.update_profile(patch)
