"""HTTP layer for `/api/privacy`, `/api/dossier` and `/api/interviews`.

Contract mirrors of handlers/admin.ts (privacy), handlers/dossier.ts and
handlers/interviews.ts. All endpoints require authentication; privacy is
scoped to the caller.
"""

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, get_current_principal
from app.schemas.booking import (
    BookingCatalog,
    Dossier,
    LiveSessionSnapshot,
    MyInterview,
    ScheduleRequest,
    ScheduleResponse,
)
from app.schemas.privacy import PrivacyPatch, PrivacySettings
from app.services.portal_service import BookingService, DossierService, PrivacyService

router = APIRouter(
    tags=["Portal"],
    dependencies=[Depends(get_current_principal)],
)


def _privacy() -> PrivacyService:
    return PrivacyService()


def _dossier() -> DossierService:
    return DossierService()


def _booking() -> BookingService:
    return BookingService()


# ─── Privacy ─────────────────────────────────────────────────────────────

@router.get("/privacy/settings", response_model=PrivacySettings)
async def privacy_settings(
    principal: Principal = Depends(get_current_principal),
    service: PrivacyService = Depends(_privacy),
) -> PrivacySettings:
    return await service.get(principal.user_id)


@router.patch("/privacy/settings", response_model=PrivacySettings)
async def patch_privacy(
    patch: PrivacyPatch,
    principal: Principal = Depends(get_current_principal),
    service: PrivacyService = Depends(_privacy),
) -> PrivacySettings:
    return await service.patch(principal.user_id, patch)


@router.delete("/privacy/shared-reports/{shared_id}")
async def revoke_shared_report(
    shared_id: str,
    principal: Principal = Depends(get_current_principal),
    service: PrivacyService = Depends(_privacy),
) -> dict[str, bool]:
    await service.revoke_shared_report(principal.user_id, shared_id)
    return {"ok": True}


# ─── Dossier ─────────────────────────────────────────────────────────────

@router.get("/dossier/me", response_model=Dossier)
async def my_dossier(
    principal: Principal = Depends(get_current_principal),
    service: DossierService = Depends(_dossier),
) -> Dossier:
    return await service.get_mine(principal.user_id)


@router.get("/dossier/{dossier_id}", response_model=Dossier)
async def dossier_by_id(
    dossier_id: str,
    service: DossierService = Depends(_dossier),
) -> Dossier:
    return await service.get_by_id(dossier_id)


@router.post("/dossier/{dossier_id}/share")
async def share_dossier(
    dossier_id: str,
    service: DossierService = Depends(_dossier),
) -> dict[str, Any]:
    return await service.share(dossier_id)


# ─── Interviews / booking ────────────────────────────────────────────────

@router.get("/interviews/catalog", response_model=BookingCatalog)
async def interviews_catalog(service: BookingService = Depends(_booking)) -> BookingCatalog:
    return await service.catalog()


@router.get("/interviews/catalog/{catalog_id}", response_model=BookingCatalog)
async def interviews_catalog_by_id(
    catalog_id: str,
    service: BookingService = Depends(_booking),
) -> BookingCatalog:
    return await service.catalog(catalog_id)


@router.post("/interviews/schedule", response_model=ScheduleResponse)
async def schedule_interview(
    payload: ScheduleRequest,
    service: BookingService = Depends(_booking),
) -> ScheduleResponse:
    return await service.schedule(payload)


@router.get("/interviews/session/{session_id}", response_model=LiveSessionSnapshot)
async def live_session(
    session_id: str,
    service: BookingService = Depends(_booking),
) -> LiveSessionSnapshot:
    return await service.live_session(session_id)


@router.get("/interviews/my-interviews", response_model=list[MyInterview])
async def my_interviews(service: BookingService = Depends(_booking)) -> list[MyInterview]:
    return await service.my_interviews()
