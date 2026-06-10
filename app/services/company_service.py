"""Company-portal business logic.

Pipeline moves are REAL here (the mock only echoed) — a move updates the
card's stage so the board reflects it on the next read. Credits maintain
a running ledger with month roll-ups computed from the transactions.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from ulid import ULID

from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.db.mongo import get_database
from app.schemas.company import (
    AnonymousInterviewer,
    AnonymousInterviewerCreate,
    BillingResponse,
    CandidateMatch,
    CompanyCredits,
    CompanyProfile,
    CreditMutation,
    CreditRate,
    CreditTransaction,
    FollowupSkillOption,
    FollowupTracking,
    PipelineBoard,
    PipelineCard,
    SearchFacets,
    SearchRequest,
    SearchResponse,
    TeamInvite,
    TeamMember,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    doc.pop("key", None)
    return doc


class CompanyService:
    def _db(self):
        return get_database()

    # ── Company + anonymous interviewers ────────────────────────────────

    async def company(self) -> CompanyProfile:
        doc = await self._db()["companies"].find_one({"id": "co_northstack"})
        if doc is None:
            raise RuntimeError("companies seed data missing")
        return CompanyProfile.model_validate(_strip(doc))

    async def interviewers(self) -> list[AnonymousInterviewer]:
        docs = await self._db()["anonymous_interviewers"].find().to_list(length=200)
        return [AnonymousInterviewer.model_validate(_strip(d)) for d in docs]

    async def add_interviewer(self, body: AnonymousInterviewerCreate) -> AnonymousInterviewer:
        company = await self.company()
        domain = body.email.split("@")[-1].lower() if "@" in body.email else ""
        if domain != company.primaryDomain:
            raise AppError(
                f"Email must be on @{company.primaryDomain}.",
                status_code=400,
                extra={"code": "domain_mismatch"},
            )
        doc = {
            "id": f"ai_{str(ULID()).lower()}",
            "displayName": body.displayName,
            "title": body.title,
            "email": body.email,
            "specialties": [s.strip() for s in body.specialties if s.strip()],
            "verified": False,
            "sessions": 0,
            "externalSessions": 0,
            "addedAt": _now_iso(),
        }
        await self._db()["anonymous_interviewers"].insert_one(dict(doc))
        return AnonymousInterviewer.model_validate(doc)

    async def verify_interviewer(self, interviewer_id: str) -> AnonymousInterviewer:
        updated = await self._db()["anonymous_interviewers"].find_one_and_update(
            {"id": interviewer_id}, {"$set": {"verified": True}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"Interviewer {interviewer_id} not found")
        return AnonymousInterviewer.model_validate(_strip(updated))

    async def remove_interviewer(self, interviewer_id: str) -> None:
        result = await self._db()["anonymous_interviewers"].delete_one({"id": interviewer_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Interviewer {interviewer_id} not found")

    # ── Credits ─────────────────────────────────────────────────────────

    async def _ledger(self) -> list[dict[str, Any]]:
        docs = await self._db()["credit_transactions"].find().to_list(length=2000)
        docs.sort(key=lambda d: d.get("at", ""))
        return [_strip(d) for d in docs]

    @staticmethod
    def _month_sum(ledger: list[dict[str, Any]], kind: str, now: Optional[datetime] = None) -> int:
        now = now or datetime.now(timezone.utc)
        total = 0
        for tx in ledger:
            if tx["kind"] != kind:
                continue
            try:
                at = datetime.fromisoformat(tx["at"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if at.year == now.year and at.month == now.month:
                total += tx["amount"]
        return total

    async def credits(self) -> CompanyCredits:
        ledger = await self._ledger()
        balance = ledger[-1]["balanceAfter"] if ledger else 0
        return CompanyCredits(
            balance=balance,
            earnedThisMonth=self._month_sum(ledger, "earned"),
            spentThisMonth=self._month_sum(ledger, "spent"),
            ledger=[CreditTransaction.model_validate(t) for t in ledger],
        )

    async def _apply_tx(self, kind: str, body: CreditMutation) -> CompanyCredits:
        ledger = await self._ledger()
        balance = ledger[-1]["balanceAfter"] if ledger else 0
        if kind == "spent" and body.amount > balance:
            raise AppError("insufficient credits", status_code=402)
        new_balance = balance + body.amount if kind == "earned" else balance - body.amount
        tx = {
            "id": f"tx_{str(ULID()).lower()}",
            "at": _now_iso(),
            "kind": kind,
            "amount": body.amount,
            "reason": body.reason,
            "balanceAfter": new_balance,
            "interviewerId": body.interviewerId,
        }
        await self._db()["credit_transactions"].insert_one(dict(tx))
        if kind == "earned" and body.interviewerId:
            doc = await self._db()["anonymous_interviewers"].find_one({"id": body.interviewerId})
            if doc:
                await self._db()["anonymous_interviewers"].find_one_and_update(
                    {"id": body.interviewerId},
                    {"$set": {
                        "externalSessions": doc.get("externalSessions", 0) + 1,
                        "sessions": doc.get("sessions", 0) + 1,
                    }},
                    return_document=True,
                )
        return await self.credits()

    async def earn(self, body: CreditMutation) -> CompanyCredits:
        return await self._apply_tx("earned", body)

    async def spend(self, body: CreditMutation) -> CompanyCredits:
        return await self._apply_tx("spent", body)

    async def credit_rate(self) -> CreditRate:
        doc = await self._db()["credit_rate"].find_one({"key": "default"})
        if doc is None:
            raise RuntimeError("credit_rate seed data missing")
        return CreditRate.model_validate(_strip(doc))

    async def set_credit_rate(self, rupees: float, reviewer_id: str) -> CreditRate:
        await self._db()["credit_rate"].find_one_and_update(
            {"key": "default"},
            {"$set": {
                "rupeesPerCredit": round(rupees, 2),
                "updatedAt": _now_iso(),
                "updatedBy": reviewer_id,
            }},
            return_document=True,
        )
        return await self.credit_rate()

    # ── Team + billing ──────────────────────────────────────────────────

    async def team(self) -> list[TeamMember]:
        docs = await self._db()["team_members"].find().to_list(length=200)
        return [TeamMember.model_validate(_strip(d)) for d in docs]

    async def invite_member(self, body: TeamInvite) -> TeamMember:
        name = body.email.split("@")[0].replace(".", " ").title()
        doc = {
            "id": f"tm_{str(ULID()).lower()}",
            "name": name,
            "email": body.email,
            "role": body.role,
            "pipelines": 0,
            "lastActive": "just invited",
            "status": "active",
        }
        await self._db()["team_members"].insert_one(dict(doc))
        return TeamMember.model_validate(doc)

    async def remove_member(self, member_id: str) -> None:
        result = await self._db()["team_members"].delete_one({"id": member_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Member {member_id} not found")

    async def billing(self) -> BillingResponse:
        doc = await self._db()["billing"].find_one({"key": "default"})
        if doc is None:
            raise RuntimeError("billing seed data missing")
        return BillingResponse.model_validate(_strip(doc))

    # ── Gray follow-ups ─────────────────────────────────────────────────

    async def gray_followups(self) -> list[FollowupTracking]:
        docs = await self._db()["gray_followups"].find().to_list(length=200)
        return [FollowupTracking.model_validate(_strip(d)) for d in docs]

    async def remind_followup(self, followup_id: str) -> dict[str, Any]:
        doc = await self._db()["gray_followups"].find_one({"id": followup_id})
        if doc is None:
            raise NotFoundError(f"Follow-up {followup_id} not found")
        return {"ok": True, "id": followup_id}

    async def delete_followup(self, followup_id: str) -> None:
        result = await self._db()["gray_followups"].delete_one({"id": followup_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Follow-up {followup_id} not found")

    # ── Discovery / pipeline / follow-up requests ───────────────────────

    async def search(self, body: SearchRequest) -> SearchResponse:
        docs = await self._db()["search_candidates"].find().to_list(length=200)
        candidates = [CandidateMatch.model_validate(_strip(d)) for d in docs]
        min_score = 0
        if body.filters and isinstance(body.filters.get("minScore"), (int, float)):
            min_score = body.filters["minScore"]
        facets_doc = await self._db()["search_facets"].find_one({"key": "default"}) or {}
        return SearchResponse(
            query=body.query,
            candidates=[c for c in candidates if c.verificationScore >= min_score],
            facets=SearchFacets.model_validate(_strip(facets_doc)),
        )

    async def pipeline(self) -> PipelineBoard:
        docs = await self._db()["pipeline_cards"].find().to_list(length=200)
        cards = [PipelineCard.model_validate(_strip(d)) for d in docs]
        board = PipelineBoard()
        for card in cards:
            getattr(board, card.stage).append(card)
        return board

    async def move_pipeline(self, candidate_id: str, stage: str) -> dict[str, Any]:
        updated = await self._db()["pipeline_cards"].find_one_and_update(
            {"candidateId": candidate_id}, {"$set": {"stage": stage}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"Candidate {candidate_id} not on the board")
        return {"ok": True, "candidateId": candidate_id, "stage": stage}

    async def followup_skills(self) -> list[FollowupSkillOption]:
        docs = await self._db()["followup_skills"].find().to_list(length=100)
        return [FollowupSkillOption.model_validate(_strip(d)) for d in docs]

    async def request_followup(self, candidate_id: str, skills: list[str], message: str) -> dict[str, Any]:
        if not skills:
            raise ValidationError("at least one skill required")
        request_id = f"fr_{str(ULID()).lower()}"
        await self._db()["followup_requests"].insert_one({
            "id": request_id,
            "candidateId": candidate_id,
            "skills": skills,
            "message": message,
            "createdAt": _now_iso(),
        })
        return {"ok": True, "requestId": request_id, "candidateId": candidate_id, "skills": skills, "message": message}

    # ── AI chat (canned, streamed by the API layer) ─────────────────────

    @staticmethod
    def pick_answer(prompt: str) -> str:
        p = prompt.lower()
        if "payment" in p or "idempotenc" in p:
            return (
                "I cannot answer this from existing evidence. Aarav has not been "
                "verified on payment-domain specifics. You can trigger a targeted "
                "30-minute follow-up session focused exactly on this."
            )
        if "system design" in p or "staff" in p:
            return (
                "Aarav was verified Advanced on System Design (82/100) in the Feb 02 "
                "session. Strongest signals: tradeoff reasoning and operational realism."
            )
        return (
            "Based on the evidence in Aarav’s dossier, he demonstrates solid "
            "understanding with one notable gap. Verifier validated his explanation "
            "of transactional producers and ordering guarantees; uncertain on "
            "producer-epoch fencing."
        )
