"""Assessment + coupon business logic.

ID generation: ULID-based (`asm_<ulid>`), matching every other entity —
replaces the old Mongo-era racy sequential counter (`_next_id()` counted
existing docs and padded, with a ULID fallback on collision). Confirmed
safe to change: `assessment.id` is never rendered as visible text in the
frontend (only used as a React key/data-testid/mutation payload — see
the migration plan's Stage 4 notes), and there's no live data to
preserve continuity for.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.exceptions import ConflictError, NotFoundError
from app.models.assessment import Assessment as AssessmentModel
from app.models.assessment import AssessmentBot
from app.models.assessment import Coupon as CouponModel
from app.schemas.assessment import (
    AdminAssessment,
    AssessmentFull,
    AssessmentFullCreate,
    AssessmentFullUpdate,
    CatalogAssessment,
    Coupon,
    CouponCode,
    CouponCreate,
)


def _assessment_id() -> str:
    return f"asm_{ULID()}"


def _to_schema(row: AssessmentModel) -> AssessmentFull:
    return AssessmentFull(
        id=row.id,
        slug=row.slug,
        title=row.title,
        domain=row.domain,  # type: ignore[arg-type]
        depth=row.depth,  # type: ignore[arg-type]
        type=row.type,  # type: ignore[arg-type]
        duration=row.duration,
        price=row.price,
        available=row.available,
        popular=row.popular,
        published=row.published,
        description=row.description,
        tags=list(row.tags or []),
        probes=list(row.probes or []),
        botIds=[link.bot_id for link in row.bot_links],
        sessions=row.sessions,
    )


class AssessmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_full(self) -> list[AssessmentFull]:
        stmt = select(AssessmentModel).order_by(AssessmentModel.id)
        rows = (await self.db.execute(stmt)).scalars().unique().all()
        return [_to_schema(r) for r in rows]

    async def list_admin(self) -> list[AdminAssessment]:
        return [AdminAssessment.model_validate(a.model_dump()) for a in await self.list_full()]

    async def list_catalog(self) -> list[CatalogAssessment]:
        published = [a for a in await self.list_full() if a.published]
        return [CatalogAssessment.model_validate(a.model_dump()) for a in published]

    async def list_catalog_full(self) -> list[AssessmentFull]:
        return [a for a in await self.list_full() if a.published]

    async def create(self, payload: AssessmentFullCreate) -> AssessmentFull:
        row = AssessmentModel(
            id=_assessment_id(),
            slug=payload.slug or f"a-{str(ULID()).lower()}",
            title=payload.title or "New assessment",
            domain=payload.domain or "Backend",
            depth=payload.depth or "Intermediate",
            type=payload.type or "bot",
            duration=payload.duration if payload.duration is not None else 60,
            price=payload.price if payload.price is not None else 0,
            available=payload.available if payload.available is not None else 4,
            popular=False,
            published=False,  # new assessments always start unpublished
            description=payload.description or "",
            tags=payload.tags or [],
            probes=payload.probes or [],
            sessions=0,
        )
        row.bot_links = [AssessmentBot(bot_id=b) for b in (payload.botIds or [])]
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row, attribute_names=["bot_links"])
        return _to_schema(row)

    async def update(self, item_id: str, patch: AssessmentFullUpdate) -> AssessmentFull:
        row = await self.db.get(AssessmentModel, item_id)
        if row is None:
            raise NotFoundError(f"Assessment {item_id} not found")
        diff = patch.model_dump(exclude_unset=True)
        bot_ids = diff.pop("botIds", None)
        for key, value in diff.items():
            setattr(row, key, value)
        if bot_ids is not None:
            for link in list(row.bot_links):
                await self.db.delete(link)
            await self.db.flush()
            row.bot_links = [AssessmentBot(bot_id=b) for b in bot_ids]
        await self.db.flush()
        await self.db.refresh(row, attribute_names=["bot_links"])
        return _to_schema(row)

    async def toggle_publish(self, item_id: str) -> AssessmentFull:
        row = await self.db.get(AssessmentModel, item_id)
        if row is None:
            raise NotFoundError(f"Assessment {item_id} not found")
        row.published = not row.published
        await self.db.flush()
        return _to_schema(row)

    async def delete(self, item_id: str) -> None:
        row = await self.db.get(AssessmentModel, item_id)
        if row is None:
            raise NotFoundError(f"Assessment {item_id} not found")
        await self.db.delete(row)
        await self.db.flush()


def _coupon_to_schema(row: CouponModel) -> Coupon:
    return Coupon(code=row.code, type=row.type, value=row.value, desc=row.desc, active=row.active)  # type: ignore[arg-type]


class CouponService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[Coupon]:
        stmt = select(CouponModel).order_by(CouponModel.code)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_coupon_to_schema(r) for r in rows]

    async def list_active_codes(self) -> list[CouponCode]:
        active = [c for c in await self.list_all() if c.active]
        return [CouponCode.model_validate(c.model_dump()) for c in active]

    async def create(self, payload: CouponCreate) -> Coupon:
        code = payload.code.strip().upper()
        if await self.db.get(CouponModel, code):
            raise ConflictError(f"Coupon {code} already exists")
        row = CouponModel(code=code, type=payload.type, value=payload.value, desc=payload.desc, active=True)
        self.db.add(row)
        await self.db.flush()
        return _coupon_to_schema(row)

    async def toggle(self, code: str) -> Coupon:
        row = await self.db.get(CouponModel, code)
        if row is None:
            raise NotFoundError(f"Coupon {code} not found")
        row.active = not row.active
        await self.db.flush()
        return _coupon_to_schema(row)

    async def delete(self, code: str) -> None:
        row = await self.db.get(CouponModel, code)
        if row is None:
            raise NotFoundError(f"Coupon {code} not found")
        await self.db.delete(row)
        await self.db.flush()
