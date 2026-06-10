"""Assessment + coupon business logic.

ID convention mirrors the mock for parity: ASS-<zero-padded sequence>.
On a collision (concurrent insert) we fall back to a ULID-suffixed id —
the unique index on `id` is the backstop.
"""

from typing import Any, Optional

from ulid import ULID

from app.core.exceptions import ConflictError, NotFoundError
from app.db.mongo import get_database
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


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    return doc


class AssessmentService:
    def _coll(self):
        return get_database()["assessments"]

    async def _next_id(self) -> str:
        docs = await self._coll().find().to_list(length=2000)
        n = len(docs) + 1
        candidate = f"ASS-{n:03d}"
        if any(d.get("id") == candidate for d in docs):
            return f"ASS-{ULID()}"
        return candidate

    async def list_full(self) -> list[AssessmentFull]:
        docs = await self._coll().find().to_list(length=2000)
        return [AssessmentFull.model_validate(_strip(d)) for d in docs]

    async def list_admin(self) -> list[AdminAssessment]:
        return [AdminAssessment.model_validate(a.model_dump()) for a in await self.list_full()]

    async def list_catalog(self) -> list[CatalogAssessment]:
        published = [a for a in await self.list_full() if a.published]
        return [CatalogAssessment.model_validate(a.model_dump()) for a in published]

    async def list_catalog_full(self) -> list[AssessmentFull]:
        return [a for a in await self.list_full() if a.published]

    async def create(self, payload: AssessmentFullCreate) -> AssessmentFull:
        new_id = await self._next_id()
        doc = {
            "id": new_id,
            "slug": payload.slug or f"a-{str(ULID()).lower()}",
            "title": payload.title or "New assessment",
            "domain": payload.domain or "Backend",
            "depth": payload.depth or "Intermediate",
            "type": payload.type or "bot",
            "duration": payload.duration if payload.duration is not None else 60,
            "price": payload.price if payload.price is not None else 0,
            "available": payload.available if payload.available is not None else 4,
            "popular": False,
            "published": False,  # new assessments always start unpublished
            "description": payload.description or "",
            "tags": payload.tags or [],
            "probes": payload.probes or [],
            "botIds": payload.botIds or [],
            "sessions": 0,
        }
        await self._coll().insert_one(doc)
        return AssessmentFull.model_validate(_strip(doc))

    async def update(self, item_id: str, patch: AssessmentFullUpdate) -> AssessmentFull:
        diff = patch.model_dump(exclude_unset=True)
        updated = await self._coll().find_one_and_update(
            {"id": item_id}, {"$set": diff}, return_document=True
        ) if diff else await self._coll().find_one({"id": item_id})
        if updated is None:
            raise NotFoundError(f"Assessment {item_id} not found")
        return AssessmentFull.model_validate(_strip(updated))

    async def toggle_publish(self, item_id: str) -> AssessmentFull:
        current = await self._coll().find_one({"id": item_id})
        if current is None:
            raise NotFoundError(f"Assessment {item_id} not found")
        updated = await self._coll().find_one_and_update(
            {"id": item_id},
            {"$set": {"published": not current.get("published", False)}},
            return_document=True,
        )
        return AssessmentFull.model_validate(_strip(updated))

    async def delete(self, item_id: str) -> None:
        result = await self._coll().delete_one({"id": item_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Assessment {item_id} not found")


class CouponService:
    def _coll(self):
        return get_database()["coupons"]

    async def list_all(self) -> list[Coupon]:
        docs = await self._coll().find().to_list(length=500)
        return [Coupon.model_validate(_strip(d)) for d in docs]

    async def list_active_codes(self) -> list[CouponCode]:
        active = [c for c in await self.list_all() if c.active]
        return [CouponCode.model_validate(c.model_dump()) for c in active]

    async def create(self, payload: CouponCreate) -> Coupon:
        code = payload.code.strip().upper()
        if await self._coll().find_one({"code": code}):
            raise ConflictError(f"Coupon {code} already exists")
        doc = {**payload.model_dump(), "code": code, "active": True}
        await self._coll().insert_one(doc)
        return Coupon.model_validate(_strip(doc))

    async def toggle(self, code: str) -> Coupon:
        current = await self._coll().find_one({"code": code})
        if current is None:
            raise NotFoundError(f"Coupon {code} not found")
        updated = await self._coll().find_one_and_update(
            {"code": code},
            {"$set": {"active": not current.get("active", True)}},
            return_document=True,
        )
        return Coupon.model_validate(_strip(updated))

    async def delete(self, code: str) -> None:
        result = await self._coll().delete_one({"code": code})
        if result.deleted_count != 1:
            raise NotFoundError(f"Coupon {code} not found")
