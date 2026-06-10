"""Privacy, dossier and booking flows."""

import time
from typing import Any, Optional

from ulid import ULID

from app.core.exceptions import NotFoundError
from app.core.privacy import MASKED_VERIFIER
from app.db.mongo import get_database
from app.schemas.booking import (
    BookingCatalog,
    Dossier,
    LiveSessionSnapshot,
    MyInterview,
    ScheduleRequest,
    ScheduleResponse,
)
from app.schemas.privacy import PrivacyPatch, PrivacySettings

_FALLBACK_USER = "usr_cand_001"


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    return doc


class PrivacyService:
    def _coll(self):
        return get_database()["privacy_settings"]

    async def _doc_for(self, user_id: Optional[str]) -> dict[str, Any]:
        doc = None
        if user_id:
            doc = await self._coll().find_one({"userId": user_id})
        if doc is None:
            doc = await self._coll().find_one({"userId": _FALLBACK_USER})
        if doc is None:
            raise RuntimeError("privacy_settings seed data missing")
        return doc

    async def get(self, user_id: Optional[str]) -> PrivacySettings:
        doc = await self._doc_for(user_id)
        cleaned = _strip(doc)
        cleaned.pop("userId", None)
        return PrivacySettings.model_validate(cleaned)

    async def patch(self, user_id: Optional[str], patch: PrivacyPatch) -> PrivacySettings:
        doc = await self._doc_for(user_id)
        diff = patch.model_dump(exclude_unset=True)
        if diff:
            await self._coll().find_one_and_update(
                {"userId": doc["userId"]}, {"$set": diff}, return_document=True
            )
        return await self.get(user_id)

    async def revoke_shared_report(self, user_id: Optional[str], shared_id: str) -> None:
        doc = await self._doc_for(user_id)
        remaining = [r for r in doc.get("sharedReports", []) if r.get("id") != shared_id]
        await self._coll().find_one_and_update(
            {"userId": doc["userId"]},
            {"$set": {"sharedReports": remaining}},
            return_document=True,
        )


class DossierService:
    def _coll(self):
        return get_database()["dossiers"]

    async def get_mine(self, user_id: Optional[str]) -> Dossier:
        doc = None
        if user_id:
            doc = await self._coll().find_one({"candidateId": user_id})
        if doc is None:
            doc = await self._coll().find_one({"candidateId": _FALLBACK_USER})
        if doc is None:
            raise RuntimeError("dossiers seed data missing")
        return Dossier.model_validate(_strip(doc))

    async def get_by_id(self, dossier_id: str) -> Dossier:
        doc = await self._coll().find_one({"id": dossier_id})
        if doc is None:
            # Mock parity — any id resolves to the seeded dossier.
            doc = await self._coll().find_one({"candidateId": _FALLBACK_USER})
        if doc is None:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        return Dossier.model_validate(_strip(doc))

    async def share(self, dossier_id: str) -> dict[str, Any]:
        dossier = await self.get_by_id(dossier_id)
        await self._coll().find_one_and_update(
            {"id": dossier.id}, {"$set": {"isShared": True}}, return_document=True
        )
        return {"ok": True, "shareUrl": f"https://anveksha.app/d/{dossier.id}"}


class BookingService:
    def _db(self):
        return get_database()

    async def catalog(self, catalog_id: Optional[str] = None) -> BookingCatalog:
        coll = self._db()["booking_catalogs"]
        doc = None
        if catalog_id:
            doc = await coll.find_one({"catalogId": catalog_id})
        if doc is None:
            doc = await coll.find_one({"catalogId": "KAF-204"})
        if doc is None:
            raise RuntimeError("booking_catalogs seed data missing")
        cleaned = _strip(doc)
        # PHI rule: candidates never learn WHICH verifier they're paired
        # with at booking time. Ratings stay visible (quality signal);
        # identity does not.
        for slots in cleaned.get("slotsByDay", {}).values():
            for slot in slots:
                slot["verifier"] = MASKED_VERIFIER
        return BookingCatalog.model_validate(cleaned)

    async def schedule(self, payload: ScheduleRequest) -> ScheduleResponse:
        catalog = await self.catalog()
        booking_id = f"int_{str(ULID()).lower()}"
        scheduled_date = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        doc = {
            "id": booking_id,
            "status": "scheduled",
            "scheduled_date": scheduled_date,
            "dayId": payload.dayId,
            "slotId": payload.slotId,
            "catalog_id": catalog.catalogId,
            "title": catalog.skillName,
        }
        await self._db()["my_interviews"].insert_one(dict(doc))
        return ScheduleResponse(
            id=booking_id,
            status="scheduled",
            scheduled_date=scheduled_date,
            dayId=payload.dayId,
            slotId=payload.slotId,
            catalog=catalog,
        )

    async def live_session(self, session_id: str) -> LiveSessionSnapshot:
        doc = await self._db()["live_sessions"].find_one({"id": session_id})
        if doc is None:
            doc = await self._db()["live_sessions"].find_one({"id": "KAF-88421"})
        if doc is None:
            raise NotFoundError(f"Session {session_id} not found")
        return LiveSessionSnapshot.model_validate(_strip(doc))

    async def my_interviews(self) -> list[MyInterview]:
        docs = await self._db()["my_interviews"].find().to_list(length=200)
        return [MyInterview.model_validate(_strip(d)) for d in docs]
