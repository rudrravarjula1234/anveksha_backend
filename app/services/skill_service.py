"""Skill-ledger reads.

The ledger is the composite powering the Candidate Profile page. It's
stored denormalised per user in `skill_ledgers` — one document per
candidate, exactly the shape the frontend renders. Mutations (new
verification session, authority granted) will update this document in
later modules.

Fallback rule mirrors the mock: unknown or unauthenticated callers get
Aarav's ledger so the page always renders.
"""

from typing import Optional

from app.db.mongo import get_database
from app.schemas.skill import SkillLedger

_FALLBACK_CANDIDATE_ID = "usr_cand_001"


class SkillService:
    def _coll(self):
        return get_database()["skill_ledgers"]

    async def ledger_for_user(self, user_id: Optional[str]) -> SkillLedger:
        doc = None
        if user_id:
            doc = await self._coll().find_one({"candidateId": user_id})
        if doc is None:
            doc = await self._coll().find_one({"candidateId": _FALLBACK_CANDIDATE_ID})
        if doc is None:
            # Seeds missing — fail loudly rather than fabricate an empty page.
            raise RuntimeError("skill_ledgers seed data missing")
        doc.pop("_id", None)
        return SkillLedger.model_validate(doc)
