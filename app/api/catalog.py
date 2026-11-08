"""HTTP layer for `/api/catalog` — candidate-facing assessment catalog.

Published assessments only. Any authenticated user can browse.

    GET /api/catalog          — slim catalog rows
    GET /api/catalog/full     — full assessment objects (published)
    GET /api/catalog/coupons  — active coupons (no `active` flag on wire)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_principal
from app.db.session import get_session
from app.schemas.assessment import AssessmentFull, CatalogAssessment, CouponCode
from app.services.assessment_service import AssessmentService, CouponService

router = APIRouter(
    tags=["Catalog"],
    dependencies=[Depends(get_current_principal)],
)


def _assessments(db: AsyncSession = Depends(get_session)) -> AssessmentService:
    return AssessmentService(db)


def _coupons(db: AsyncSession = Depends(get_session)) -> CouponService:
    return CouponService(db)


@router.get("", response_model=list[CatalogAssessment])
async def catalog(service: AssessmentService = Depends(_assessments)) -> list[CatalogAssessment]:
    return await service.list_catalog()


@router.get("/full", response_model=list[AssessmentFull])
async def catalog_full(service: AssessmentService = Depends(_assessments)) -> list[AssessmentFull]:
    return await service.list_catalog_full()


@router.get("/coupons", response_model=list[CouponCode])
async def catalog_coupons(service: CouponService = Depends(_coupons)) -> list[CouponCode]:
    return await service.list_active_codes()
