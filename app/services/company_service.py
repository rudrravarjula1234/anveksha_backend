"""Company-portal business logic.

Pipeline moves are REAL here (the mock only echoed) — a move updates the
card's stage so the board reflects it on the next read. Credits maintain
a MAINTAINED balance column on `companies` (updated transactionally
alongside each `credit_transactions` insert) rather than recomputing it
by loading and sorting the whole ledger on every read — see
app/models/company.py's module docstring for why.
"""

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.core.privacy import candidate_alias, mask_initials
from app.core.timefmt import to_wire, utc_now
from app.models.company import AnonymousInterviewer as InterviewerModel
from app.models.company import Billing as BillingModel
from app.models.company import Company as CompanyModel
from app.models.company import CompanyUnlock as CompanyUnlockModel
from app.models.company import CreditRate as CreditRateModel
from app.models.company import CreditTransaction as CreditTransactionModel
from app.models.company import FollowupRequest as FollowupRequestModel
from app.models.company import FollowupSkillOption as FollowupSkillModel
from app.models.company import GrayFollowup as GrayFollowupModel
from app.models.company import PipelineCard as PipelineCardModel
from app.models.company import SearchCandidate as SearchCandidateModel
from app.models.company import SearchFacets as SearchFacetsModel
from app.models.company import TeamMember as TeamMemberModel
from app.schemas.company import (
    AnonymousInterviewer,
    AnonymousInterviewerCreate,
    BillingResponse,
    BillingSummary,
    CandidateMatch,
    CompanyCredits,
    CompanyProfile,
    CreditMutation,
    CreditRate,
    CreditTransaction,
    FollowupSkillOption,
    FollowupTracking,
    Invoice,
    PipelineBoard,
    PipelineCard,
    SearchFacet,
    SearchFacets,
    SearchRequest,
    SearchResponse,
    TeamInvite,
    TeamMember,
)

_COMPANY_ID = "co_northstack"


def _interviewer_to_schema(row: InterviewerModel) -> AnonymousInterviewer:
    return AnonymousInterviewer(
        id=row.id, displayName=row.display_name, title=row.title, email=row.email,
        specialties=list(row.specialties or []), verified=row.verified, sessions=row.sessions,
        externalSessions=row.external_sessions, rating=row.rating, addedAt=to_wire(row.added_at),
    )


def _tx_to_schema(row: CreditTransactionModel) -> CreditTransaction:
    return CreditTransaction(
        id=row.id, at=to_wire(row.at), kind=row.kind, amount=row.amount, reason=row.reason,  # type: ignore[arg-type]
        balanceAfter=row.balance_after, interviewerId=row.interviewer_id,
    )


def _member_to_schema(row: TeamMemberModel) -> TeamMember:
    return TeamMember(
        id=row.id, name=row.name, email=row.email, role=row.role, pipelines=row.pipelines,  # type: ignore[arg-type]
        lastActive=row.last_active, status=row.status,  # type: ignore[arg-type]
    )


def _followup_to_schema(row: GrayFollowupModel) -> FollowupTracking:
    return FollowupTracking(
        id=row.id, candidate=row.candidate, candidateId=row.candidate_id, grayArea=row.gray_area,
        asked=row.asked, requested=row.requested, status=row.status, companies=row.companies,  # type: ignore[arg-type]
        scheduled=row.scheduled, score=row.score,
    )


class CompanyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Company + anonymous interviewers ────────────────────────────────

    async def _company_row(self) -> CompanyModel:
        row = await self.db.get(CompanyModel, _COMPANY_ID)
        if row is None:
            raise RuntimeError("companies seed data missing")
        return row

    async def company(self) -> CompanyProfile:
        row = await self._company_row()
        return CompanyProfile(id=row.id, name=row.name, primaryDomain=row.primary_domain)

    async def interviewers(self) -> list[AnonymousInterviewer]:
        stmt = select(InterviewerModel).order_by(InterviewerModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_interviewer_to_schema(r) for r in rows]

    async def add_interviewer(self, body: AnonymousInterviewerCreate) -> AnonymousInterviewer:
        company = await self.company()
        domain = body.email.split("@")[-1].lower() if "@" in body.email else ""
        if domain != company.primaryDomain:
            raise AppError(
                f"Email must be on @{company.primaryDomain}.",
                status_code=400,
                extra={"code": "domain_mismatch"},
            )
        row = InterviewerModel(
            id=f"ai_{str(ULID()).lower()}",
            display_name=body.displayName,
            title=body.title,
            email=body.email,
            specialties=[s.strip() for s in body.specialties if s.strip()],
            verified=False,
            sessions=0,
            external_sessions=0,
            added_at=utc_now(),
        )
        self.db.add(row)
        await self.db.flush()
        return _interviewer_to_schema(row)

    async def verify_interviewer(self, interviewer_id: str) -> AnonymousInterviewer:
        row = await self.db.get(InterviewerModel, interviewer_id)
        if row is None:
            raise NotFoundError(f"Interviewer {interviewer_id} not found")
        row.verified = True
        await self.db.flush()
        return _interviewer_to_schema(row)

    async def remove_interviewer(self, interviewer_id: str) -> None:
        row = await self.db.get(InterviewerModel, interviewer_id)
        if row is None:
            raise NotFoundError(f"Interviewer {interviewer_id} not found")
        await self.db.delete(row)
        await self.db.flush()

    # ── Credits ─────────────────────────────────────────────────────────

    @staticmethod
    def _month_bounds(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
        now = now or utc_now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, next_month

    async def _month_sums(self) -> dict[str, int]:
        """`earned` + `spent` totals for the current month in ONE grouped
        query (H3) — the old code ran a separate `SUM` per kind. The
        `kind IN (...)` predicate keeps it sargable for the existing
        `(kind, at)` index.
        """
        start, end = self._month_bounds()
        stmt = (
            select(
                CreditTransactionModel.kind,
                func.coalesce(func.sum(CreditTransactionModel.amount), 0),
            )
            .where(
                CreditTransactionModel.kind.in_(("earned", "spent")),
                CreditTransactionModel.at >= start,
                CreditTransactionModel.at < end,
            )
            .group_by(CreditTransactionModel.kind)
        )
        return {kind: total for kind, total in (await self.db.execute(stmt)).all()}

    async def _ledger_rows(self) -> list[CreditTransactionModel]:
        # Safety cap, not real pagination — most recent 1000 transactions,
        # re-sorted back to chronological order for display.
        stmt = select(CreditTransactionModel).order_by(CreditTransactionModel.at.desc()).limit(1000)
        return list(reversed((await self.db.execute(stmt)).scalars().all()))

    @staticmethod
    def _credits_response(
        balance: int, sums: dict[str, int], rows: list[CreditTransactionModel]
    ) -> CompanyCredits:
        return CompanyCredits(
            balance=balance,
            earnedThisMonth=sums.get("earned", 0),
            spentThisMonth=sums.get("spent", 0),
            ledger=[_tx_to_schema(r) for r in rows],
        )

    async def credits(self) -> CompanyCredits:
        company = await self._company_row()
        rows = await self._ledger_rows()
        sums = await self._month_sums()
        return self._credits_response(company.credit_balance, sums, rows)

    async def _apply_tx(self, kind: str, body: CreditMutation) -> CompanyCredits:
        # One conditional UPDATE ... RETURNING: the balance check and the
        # write are a single statement, and the row lock it takes serialises
        # concurrent spends until commit (a read-then-write in Python let two
        # spends both pass the check). `ck_companies_credit_balance_nonneg`
        # backstops it at the schema level.
        delta = body.amount if kind == "earned" else -body.amount
        stmt = update(CompanyModel).where(CompanyModel.id == _COMPANY_ID)
        if kind == "spent":
            stmt = stmt.where(CompanyModel.credit_balance >= body.amount)
        stmt = (
            stmt.values(credit_balance=CompanyModel.credit_balance + delta)
            .returning(CompanyModel.credit_balance)
            .execution_options(synchronize_session="fetch")
        )
        new_balance = (await self.db.execute(stmt)).scalar_one_or_none()
        if new_balance is None:
            await self._company_row()  # raises if the seed row is missing
            raise AppError("insufficient credits", status_code=402)
        tx = CreditTransactionModel(
            id=f"tx_{str(ULID()).lower()}",
            at=utc_now(),
            kind=kind,
            amount=body.amount,
            reason=body.reason,
            balance_after=new_balance,
            interviewer_id=body.interviewerId,
        )
        self.db.add(tx)
        if kind == "earned" and body.interviewerId:
            # SQL-side increment; a Python `+=` loses updates under concurrency.
            await self.db.execute(
                update(InterviewerModel)
                .where(InterviewerModel.id == body.interviewerId)
                .values(
                    external_sessions=InterviewerModel.external_sessions + 1,
                    sessions=InterviewerModel.sessions + 1,
                )
                .execution_options(synchronize_session="fetch")
            )
        await self.db.flush()
        # H3: build the response from state we already have — the old path
        # re-read the company row (redundant; `new_balance` is authoritative
        # in this transaction) and issued two separate month-SUM queries.
        sums = await self._month_sums()
        rows = await self._ledger_rows()
        return self._credits_response(new_balance, sums, rows)

    async def earn(self, body: CreditMutation) -> CompanyCredits:
        return await self._apply_tx("earned", body)

    async def spend(self, body: CreditMutation) -> CompanyCredits:
        return await self._apply_tx("spent", body)

    async def credit_rate(self) -> CreditRate:
        row = await self.db.get(CreditRateModel, "default")
        if row is None:
            raise RuntimeError("credit_rate seed data missing")
        return CreditRate(
            rupeesPerCredit=row.rupees_per_credit, updatedAt=to_wire(row.rate_updated_at), updatedBy=row.updated_by
        )

    async def set_credit_rate(self, rupees: float, reviewer_id: str) -> CreditRate:
        row = await self.db.get(CreditRateModel, "default")
        if row is None:
            raise RuntimeError("credit_rate seed data missing")
        row.rupees_per_credit = round(rupees, 2)
        row.rate_updated_at = utc_now()
        row.updated_by = reviewer_id
        await self.db.flush()
        return await self.credit_rate()

    # ── Team + billing ──────────────────────────────────────────────────

    async def team(self) -> list[TeamMember]:
        stmt = select(TeamMemberModel).order_by(TeamMemberModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_member_to_schema(r) for r in rows]

    async def invite_member(self, body: TeamInvite) -> TeamMember:
        name = body.email.split("@")[0].replace(".", " ").title()
        row = TeamMemberModel(
            id=f"tm_{str(ULID()).lower()}", name=name, email=body.email, role=body.role,
            pipelines=0, last_active="just invited", status="active",
        )
        self.db.add(row)
        await self.db.flush()
        return _member_to_schema(row)

    async def remove_member(self, member_id: str) -> None:
        row = await self.db.get(TeamMemberModel, member_id)
        if row is None:
            raise NotFoundError(f"Member {member_id} not found")
        await self.db.delete(row)
        await self.db.flush()

    async def billing(self) -> BillingResponse:
        row = await self.db.get(BillingModel, "default")
        if row is None:
            raise RuntimeError("billing seed data missing")
        summary = BillingSummary(
            plan=row.plan, seats=row.seats, seatsUsed=row.seats_used, monthlyAmount=row.monthly_amount,  # type: ignore[arg-type]
            nextBilling=row.next_billing, includes=list(row.includes or []),
            aiChatsUsed=row.ai_chats_used, aiChatsIncluded=row.ai_chats_included,
        )
        invoices = [
            Invoice(id=i["id"], month=i["month"], amount=i["amount"], status=i["status"], pdfUrl=i["pdf_url"])
            for i in row.invoices
        ]
        return BillingResponse(summary=summary, invoices=invoices)

    # ── Gray follow-ups ─────────────────────────────────────────────────

    async def gray_followups(self) -> list[FollowupTracking]:
        stmt = select(GrayFollowupModel).order_by(GrayFollowupModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_followup_to_schema(r) for r in rows]

    async def remind_followup(self, followup_id: str) -> dict[str, Any]:
        row = await self.db.get(GrayFollowupModel, followup_id)
        if row is None:
            raise NotFoundError(f"Follow-up {followup_id} not found")
        return {"ok": True, "id": followup_id}

    async def delete_followup(self, followup_id: str) -> None:
        row = await self.db.get(GrayFollowupModel, followup_id)
        if row is None:
            raise NotFoundError(f"Follow-up {followup_id} not found")
        await self.db.delete(row)
        await self.db.flush()

    # ── PHI: candidate unlock gating ────────────────────────────────────

    UNLOCK_COST = 50  # credits per candidate unlock

    async def is_unlocked(self, candidate_id: str) -> bool:
        return await self.db.get(CompanyUnlockModel, candidate_id) is not None

    async def _unlocked_ids(self, candidate_ids: list[str]) -> set[str]:
        """Which of `candidate_ids` are unlocked: a PK lookup scoped to the
        rows on screen, not a load of every unlock the company ever made."""
        if not candidate_ids:
            return set()
        stmt = select(CompanyUnlockModel.candidate_id).where(CompanyUnlockModel.candidate_id.in_(candidate_ids))
        return set((await self.db.execute(stmt)).scalars().all())

    async def unlock_candidate(self, candidate_id: str) -> dict[str, Any]:
        """Spend credits to reveal a candidate's identity."""
        target = await self.db.get(SearchCandidateModel, candidate_id)
        if target is None:
            raise NotFoundError(f"Candidate {candidate_id} not found")
        already = {"ok": True, "alreadyUnlocked": True, "candidateId": candidate_id}
        if await self.is_unlocked(candidate_id):
            return already
        try:
            # One savepoint for the charge and the unlock: if a concurrent
            # request unlocked this candidate first, the insert conflicts and
            # the charge is rolled back with it, so it answers like a repeat.
            async with self.db.begin_nested():
                credits = await self.spend(CreditMutation(
                    amount=self.UNLOCK_COST,
                    reason=f"Unlock candidate · {candidate_id}",
                ))
                self.db.add(CompanyUnlockModel(candidate_id=candidate_id, unlocked_at=utc_now()))
        except IntegrityError:
            return already
        return {
            "ok": True,
            "candidateId": candidate_id,
            "candidate": {
                "id": target.id, "name": target.name, "initials": target.initials, "title": target.title,
                "years": target.years, "location": target.location,
                "verificationScore": target.verification_score, "matchPercent": target.match_percent,
                "verifiedSkills": list(target.verified_skills or []),
                "graySkills": list(target.gray_skills or []), "lastActivity": target.last_activity,
            },
            "balance": credits.balance,
        }

    # ── Discovery / pipeline / follow-up requests ───────────────────────

    # M2: bounded candidate reads. The `minScore` filter runs in SQL
    # (backed by ix_search_candidates_verification_score) BEFORE the cap,
    # so a match past the first SEARCH_CAP rows by id is still returned.
    # `body.query` is echoed but not matched on: there is no text matching
    # yet, which is a product decision rather than a storage one.
    SEARCH_CAP = 500

    async def search(self, body: SearchRequest) -> SearchResponse:
        min_score = 0
        if body.filters and isinstance(body.filters.get("minScore"), (int, float)):
            min_score = body.filters["minScore"]
        stmt = (
            select(SearchCandidateModel)
            .where(SearchCandidateModel.verification_score >= min_score)
            .order_by(SearchCandidateModel.id)
            .limit(self.SEARCH_CAP)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        unlocked = await self._unlocked_ids([r.id for r in rows])
        matches: list[CandidateMatch] = []
        for row in rows:
            locked = row.id not in unlocked
            name, initials, location = row.name, row.initials, row.location
            alias = None
            if locked:
                alias, initials = candidate_alias(row.id), mask_initials()
                name, location = alias, "Unlock to reveal"
            matches.append(
                CandidateMatch(
                    id=row.id, name=name, initials=initials, title=row.title, years=row.years,
                    location=location, verificationScore=row.verification_score,
                    matchPercent=row.match_percent, verifiedSkills=list(row.verified_skills or []),
                    graySkills=list(row.gray_skills or []), lastActivity=row.last_activity,
                    locked=locked or None, alias=alias,
                )
            )
        facets_row = await self.db.get(SearchFacetsModel, "default")
        facets = SearchFacets(
            skills=[SearchFacet(**s) for s in (facets_row.skills if facets_row else [])],
            locations=[SearchFacet(**loc) for loc in (facets_row.locations if facets_row else [])],
        )
        return SearchResponse(
            query=body.query,
            candidates=matches,
            facets=facets,
        )

    async def pipeline(self) -> PipelineBoard:
        stmt = select(PipelineCardModel).order_by(PipelineCardModel.candidate_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        unlocked = await self._unlocked_ids([r.candidate_id for r in rows])
        board = PipelineBoard()
        for row in rows:
            name, initials = row.name, row.initials
            if row.candidate_id not in unlocked:
                name = candidate_alias(row.candidate_id)
                initials = mask_initials()
            card = PipelineCard(
                candidateId=row.candidate_id, name=name, initials=initials, matchPercent=row.match_percent,
                lastActivity=row.last_activity, stage=row.stage, note=row.note,  # type: ignore[arg-type]
            )
            getattr(board, card.stage).append(card)
        return board

    async def move_pipeline(self, candidate_id: str, stage: str) -> dict[str, Any]:
        row = await self.db.get(PipelineCardModel, candidate_id)
        if row is None:
            raise NotFoundError(f"Candidate {candidate_id} not on the board")
        row.stage = stage
        await self.db.flush()
        return {"ok": True, "candidateId": candidate_id, "stage": stage}

    async def followup_skills(self) -> list[FollowupSkillOption]:
        stmt = select(FollowupSkillModel).order_by(FollowupSkillModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [FollowupSkillOption(id=r.id, name=r.name, requested=r.requested) for r in rows]

    async def request_followup(self, candidate_id: str, skills: list[str], message: str) -> dict[str, Any]:
        if not skills:
            raise ValidationError("at least one skill required")
        request_id = f"fr_{str(ULID()).lower()}"
        self.db.add(
            FollowupRequestModel(
                id=request_id, candidate_id=candidate_id, skills=skills, message=message,
                requested_at=utc_now(),
            )
        )
        await self.db.flush()
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
