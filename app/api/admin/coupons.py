"""HTTP layer for `/api/admin/coupons` — admin coupon management.

Contract mirror of the adminRich mock: list, create, toggle by code,
delete by code.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_roles
from app.db.session import get_session
from app.schemas.assessment import Coupon, CouponCreate
from app.services.assessment_service import CouponService

router = APIRouter(
    tags=["Admin · Coupons"],
    dependencies=[Depends(require_roles("admin"))],
)


def _service(db: AsyncSession = Depends(get_session)) -> CouponService:
    return CouponService(db)


@router.get("", response_model=list[Coupon])
async def list_coupons(service: CouponService = Depends(_service)) -> list[Coupon]:
    return await service.list_all()


@router.post("", response_model=Coupon)
async def create_coupon(
    payload: CouponCreate,
    service: CouponService = Depends(_service),
) -> Coupon:
    return await service.create(payload)


@router.post("/{code}/toggle")
async def toggle_coupon(
    code: str,
    service: CouponService = Depends(_service),
) -> dict[str, bool]:
    await service.toggle(code)
    return {"ok": True}


@router.delete("/{code}")
async def delete_coupon(
    code: str,
    service: CouponService = Depends(_service),
) -> dict[str, bool]:
    await service.delete(code)
    return {"ok": True}
