"""Verifier console business logic.

Singletons read the `key: "default"` document; multi-verifier support
later swaps the key for the caller's user id without touching the API
layer.
"""

from typing import Any

from ulid import ULID

from app.core.exceptions import NotFoundError
from app.db.mongo import get_database
from app.schemas.verifier import (
    GovernanceData,
    NextSessionBrief,
    PendingReportListItem,
    ReportEnvelope,
    SessionReport,
    SuggestedGap,
    VerifierEarnings,
    VerifierProfile,
    VerifierProfileUpdate,
    VerifierQueue,
    VerifierSlot,
    VerifierSlotCreate,
)


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    doc.pop("key", None)
    return doc


class VerifierService:
    def _db(self):
        return get_database()

    async def _singleton(self, coll: str) -> dict[str, Any]:
        doc = await self._db()[coll].find_one({"key": "default"})
        if doc is None:
            raise RuntimeError(f"{coll} seed data missing")
        return _strip(doc)

    # ── Reads ───────────────────────────────────────────────────────────

    async def queue(self) -> VerifierQueue:
        return VerifierQueue.model_validate(await self._singleton("verifier_queue"))

    async def next_brief(self) -> NextSessionBrief:
        return NextSessionBrief.model_validate(await self._singleton("verifier_brief"))

    async def governance(self) -> GovernanceData:
        return GovernanceData.model_validate(await self._singleton("verifier_governance"))

    async def earnings(self) -> VerifierEarnings:
        return VerifierEarnings.model_validate(await self._singleton("verifier_earnings"))

    async def profile(self) -> VerifierProfile:
        return VerifierProfile.model_validate(await self._singleton("verifier_profile"))

    async def update_profile(self, patch: VerifierProfileUpdate) -> VerifierProfile:
        diff = patch.model_dump(exclude_unset=True)
        if diff:
            await self._db()["verifier_profile"].find_one_and_update(
                {"key": "default"}, {"$set": diff}, return_document=True
            )
        return await self.profile()

    # ── Pending reports + report editing ───────────────────────────────

    async def pending_reports(self) -> list[PendingReportListItem]:
        docs = await self._db()["pending_reports"].find().to_list(length=200)
        return [PendingReportListItem.model_validate(_strip(d)) for d in docs]

    async def _suggested_gaps(self) -> list[SuggestedGap]:
        doc = await self._singleton("verifier_suggested_gaps")
        return [SuggestedGap.model_validate(g) for g in doc.get("gaps", [])]

    async def get_report(self, report_id: str) -> ReportEnvelope:
        doc = await self._db()["session_reports"].find_one({"id": report_id})
        if doc is None:
            # Mock parity: unknown ids fall back to the first seeded report
            # so the editor pane always has content.
            doc = await self._db()["session_reports"].find_one({"id": "rpt_001"})
        if doc is None:
            raise NotFoundError(f"Report {report_id} not found")
        return ReportEnvelope(
            report=SessionReport.model_validate(_strip(doc)),
            suggestedGaps=await self._suggested_gaps(),
        )

    async def patch_report(self, report_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Free-form per-section save. The mock echoes {ok, patched, report}."""
        base = await self._db()["session_reports"].find_one({"id": report_id})
        if base is None:
            base = await self._db()["session_reports"].find_one({"id": "rpt_001"})
        if base is None:
            raise NotFoundError(f"Report {report_id} not found")
        # Whitelist the fields the editor actually patches; ignore the rest.
        allowed = {"verdict", "overallScore", "sections", "grayAreas", "strengths", "status"}
        diff = {k: v for k, v in patch.items() if k in allowed}
        if diff:
            await self._db()["session_reports"].find_one_and_update(
                {"id": base["id"]}, {"$set": diff}, return_document=True
            )
        merged = await self._db()["session_reports"].find_one({"id": base["id"]})
        return {
            "ok": True,
            "patched": patch,
            "report": SessionReport.model_validate(_strip(merged)).model_dump(),
        }

    async def publish_report(self, report_id: str) -> dict[str, Any]:
        updated = await self._db()["session_reports"].find_one_and_update(
            {"id": report_id},
            {"$set": {"status": "published"}},
            return_document=True,
        )
        if updated is not None:
            # Published reports leave the pending queue.
            await self._db()["pending_reports"].delete_one({"id": report_id})
        return {"ok": True, "status": "published"}

    # ── Slots ───────────────────────────────────────────────────────────

    async def slots(self) -> list[VerifierSlot]:
        docs = await self._db()["verifier_slots"].find().to_list(length=200)
        return [VerifierSlot.model_validate(_strip(d)) for d in docs]

    async def create_slot(self, payload: VerifierSlotCreate) -> VerifierSlot:
        doc = {
            "id": f"vs_{str(ULID()).lower()}",
            "day": payload.day or "Mon",
            "time": payload.time or "09:00",
            "duration": payload.duration or 60,
            "skill": payload.skill or "Any",
            "booked": False,
        }
        await self._db()["verifier_slots"].insert_one(doc)
        return VerifierSlot.model_validate(_strip(doc))

    async def delete_slot(self, slot_id: str) -> None:
        result = await self._db()["verifier_slots"].delete_one({"id": slot_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Slot {slot_id} not found")
