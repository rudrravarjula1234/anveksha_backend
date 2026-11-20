"""Company-portal business logic.

Pipeline moves are REAL here (the mock only echoed) — a move updates the
card's stage so the board reflects it on the next read. Credits maintain
a MAINTAINED balance column on `companies` (updated transactionally
alongside each `credit_transactions` insert) rather than recomputing it
by loading and sorting the whole ledger on every read — see
app/models/company.py's module docstring for why.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.core.privacy import candidate_alias, mask_initials
from app.core.timefmt import to_wire, utc_now
from app.models.candidate import PublicProfile as PublicProfileModel
from app.models.candidate import SkillReportDetail as SkillReportDetailModel
from app.models.session_ingest import AssessmentTranscript as AssessmentTranscriptModel
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

# Words with no discriminating value for skill/role matching — stripped
# before a query is tokenised so "someone with strong kafka experience"
# matches on "kafka", not on "someone"/"with"/"experience".
_SEARCH_STOPWORDS = frozenset(
    {
        "someone", "with", "strong", "and", "the", "for", "who", "has", "have",
        "handled", "about", "that", "this", "ideally", "comfortable", "reasoning",
        "experience", "wild", "any", "people", "person", "candidate", "engineer",
        "looking", "need", "needs", "want", "wants", "good", "great", "solid",
        "deep", "scale", "production", "prod", "someone's", "their", "they",
    }
)


def _tokenize(text: str) -> list[str]:
    """Significant lowercased terms (skills keep '.', '#', '+' — '.net',
    'c#', 'c++'). Short/stopword terms are dropped so a single stray letter
    like the test's `query: "x"` yields no tokens (→ an unfiltered list)."""
    words = re.findall(r"[a-z0-9.#+]+", text.lower())
    return [w for w in words if len(w) >= 2 and w.strip(".#+") not in _SEARCH_STOPWORDS]


def _keywords(name: str) -> list[str]:
    """Discriminating words of a gray-area / skill name, for loose matching
    of a free-text question against it (e.g. 'Kafka & Event Streams')."""
    words = re.findall(r"[a-z0-9.#+]+", name.lower())
    return [w for w in words if len(w) >= 3 and w.strip(".#+") not in _SEARCH_STOPWORDS]


# Canonical labels for common tech topics, so a company's free-text question
# about an untested area ("GCP experience?") surfaces as a cleanly-named new
# gray area instead of a raw lowercase word. Longest keys first so
# "google cloud" wins over a stray "go".
_TOPIC_VOCAB: dict[str, str] = {
    "google cloud": "Google Cloud Platform", "gcp": "Google Cloud Platform",
    "amazon web services": "AWS", "aws": "AWS", "azure": "Microsoft Azure",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes", "docker": "Docker",
    "terraform": "Terraform", "graphql": "GraphQL", "grpc": "gRPC",
    "elasticsearch": "Elasticsearch", "rabbitmq": "RabbitMQ", "redis": "Redis",
    "apache spark": "Apache Spark", "spark": "Apache Spark", "airflow": "Apache Airflow",
    "mongodb": "MongoDB", "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "machine learning": "Machine Learning", "observability": "Observability",
    "ci/cd": "CI/CD", "security": "Security", "typescript": "TypeScript",
    "react": "React", "rust": "Rust", "golang": "Go",
}

# Generic skill words that overlap too many topics to prove "already covered"
# on their own — excluded from the verified-skill guard in note_gray_interest.
_GENERIC_SKILL_WORDS = {
    "cloud", "data", "system", "systems", "design", "architecture",
    "engineering", "development", "management", "services", "service",
    "platform", "core", "web", "app", "application", "backend", "frontend",
}

# Sentence-filler words that must never be mistaken for a topic in the
# capitalized-token fallback below.
_TOPIC_STOPWORDS = {
    "how", "what", "does", "is", "would", "can", "could", "he", "his", "him",
    "any", "the", "a", "an", "on", "in", "for", "of", "to", "do", "did", "has",
    "have", "strong", "deep", "about", "with", "and", "or", "experience",
}


def _extract_topic(question: str) -> Optional[str]:
    """Name the subject of a company's question so an unverified, not-yet-gray
    topic can become a freshly-discovered gray area. Prefers a known tech term
    (``_TOPIC_VOCAB``); falls back to an acronym / capitalized word in the raw
    question. Returns None when nothing specific enough is found."""
    q = question.lower()
    for key, canon in _TOPIC_VOCAB.items():
        if key in q:
            return canon
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9.+#/]{1,}", question):
        if tok.isupper() and len(tok) >= 2 and tok.lower() not in _TOPIC_STOPWORDS:
            return tok  # an acronym like GCP, SRE, ETL
        if tok[:1].isupper() and tok.lower() not in _TOPIC_STOPWORDS and len(tok) >= 3:
            return tok  # a proper-noun-ish term like Snowflake, Kubernetes
    return None


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

    async def _credits_response(
        self, balance: int, sums: dict[str, int], rows: list[CreditTransactionModel]
    ) -> CompanyCredits:
        rate = await self.db.get(CreditRateModel, "default")
        return CompanyCredits(
            balance=balance,
            earnedThisMonth=sums.get("earned", 0),
            spentThisMonth=sums.get("spent", 0),
            ledger=[_tx_to_schema(r) for r in rows],
            rupeesPerCredit=rate.rupees_per_credit if rate is not None else None,
        )

    async def credits(self) -> CompanyCredits:
        company = await self._company_row()
        rows = await self._ledger_rows()
        sums = await self._month_sums()
        return await self._credits_response(company.credit_balance, sums, rows)

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
        return await self._credits_response(new_balance, sums, rows)

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
    # `body.query` is now matched on (keyword overlap against each
    # candidate's skills/role/name — see `_rank`): a non-trivial query keeps
    # only the candidates it actually hits and ranks them by hit count.
    SEARCH_CAP = 500

    @staticmethod
    def _rank(query: str, rows: list[SearchCandidateModel]) -> list[SearchCandidateModel]:
        """Keyword-match + rank candidates by a free-text query. An empty /
        tokenless query (e.g. the test's `"x"`) returns every row unchanged;
        otherwise only candidates matching ≥1 query term survive, ordered by
        (#terms matched, verification score)."""
        tokens = _tokenize(query)
        if not tokens:
            return list(rows)
        scored: list[tuple[int, int, SearchCandidateModel]] = []
        for row in rows:
            haystack = " ".join(
                [row.name, row.title, *(row.verified_skills or []), *(row.gray_skills or [])]
            ).lower()
            hits = sum(1 for t in set(tokens) if t in haystack)
            if hits:
                scored.append((hits, row.verification_score, row))
        scored.sort(key=lambda s: (-s[0], -s[1], s[2].id))
        return [row for _, _, row in scored]

    async def search(self, body: SearchRequest) -> SearchResponse:
        min_score = 0
        if body.filters and isinstance(body.filters.get("minScore"), (int, float)):
            min_score = body.filters["minScore"]
        stmt = (
            select(SearchCandidateModel)
            .where(SearchCandidateModel.verification_score >= min_score)
            .order_by(SearchCandidateModel.verification_score.desc(), SearchCandidateModel.id)
            .limit(self.SEARCH_CAP)
        )
        rows = self._rank(body.query, (await self.db.execute(stmt)).scalars().all())
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
            unlockCost=self.UNLOCK_COST,
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

    # ── Candidate deep-dive: real transcript/report grounding ───────────

    async def _session_transcript(self, candidate_id: str) -> Optional[AssessmentTranscriptModel]:
        """The candidate's most recent ingested interview transcript, by the
        real `candidate_user_id` FK — the search-candidate id IS the user id
        for the interviewed candidates (see seed_company_search_real.py)."""
        stmt = (
            select(AssessmentTranscriptModel)
            .where(AssessmentTranscriptModel.candidate_user_id == candidate_id)
            .order_by(AssessmentTranscriptModel.created_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalars().first()

    async def candidate_display_name(self, candidate_id: Optional[str]) -> Optional[str]:
        """The real (unmasked) name from the search pool, for addressing an
        unlocked candidate in chat. None when the id isn't in the pool."""
        if not candidate_id:
            return None
        row = await self.db.get(SearchCandidateModel, candidate_id)
        return row.name if row else None

    async def _reports(self, candidate_id: str) -> list[SkillReportDetailModel]:
        stmt = select(SkillReportDetailModel).where(SkillReportDetailModel.user_id == candidate_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def build_chat_context(
        self, candidate_id: Optional[str], question: str, *, locked: bool, ref: str
    ) -> dict[str, Any]:
        """Assemble the LLM/fallback context from the candidate's REAL rows:
        their ingested transcript (candidate turns to quote), published skill
        reports (verdict/score/strengths/gray), and public-profile gray areas
        with company demand. Nothing here is canned — it all traces to a row."""
        ctx: dict[str, Any] = {
            "task": "Answer the company's question about this candidate from session evidence only.",
            "candidateRef": ref,
            "locked": locked,
            "question": question,
        }
        if not candidate_id:
            return ctx

        transcript = await self._session_transcript(candidate_id)
        reports = await self._reports(candidate_id)
        # The report generated from THIS transcript (if any) carries the
        # session-specific verdict; otherwise fall back to the first report.
        session_report = next(
            (r for r in reports if transcript and r.transcript_id == transcript.id),
            reports[0] if reports else None,
        )

        if transcript:
            turns = [
                {"t": ln.get("t", ""), "text": ln.get("text", "")}
                for ln in (transcript.transcript or [])
                if ln.get("who") == "candidate" and ln.get("text")
            ]
            ctx["transcript"] = {
                "id": transcript.id,
                "skill": session_report.assessment_title if session_report else None,
                "candidateTurns": turns,
            }
        if session_report:
            ctx["report"] = {
                "id": session_report.id,
                "skill": session_report.assessment_title,
                "score": session_report.score,
                "verdict": session_report.verdict,
                "strengths": list(session_report.summary or []),
                "gray": list(session_report.gray or []),
            }

        profile = await self.db.get(PublicProfileModel, candidate_id)
        if profile and profile.gray_areas:
            ctx["grayAreas"] = [dict(g) for g in profile.gray_areas]
        return ctx

    async def gray_demand(self, candidate_id: str) -> list[dict[str, Any]]:
        """The candidate's gray areas ranked by how many companies have asked
        — the real signal behind the dossier page's gray-demand panel."""
        profile = await self.db.get(PublicProfileModel, candidate_id)
        grays = [dict(g) for g in (profile.gray_areas if profile else [])]
        return sorted(grays, key=lambda g: -int(g.get("companies") or 0))

    async def note_gray_interest(self, candidate_id: Optional[str], question: str) -> Optional[str]:
        """Register company demand for an unverified area, writing it back to
        public_profiles so the dossier's gray-demand panel grows on reload.

        Two cases, both real writes:
          1. The question targets a KNOWN gray area → bump its counter.
          2. The question targets something neither verified nor already-gray
             (e.g. "GCP experience?") → *discover* it as a brand-new gray area
             (companies: 1). This is what makes company questions surface gaps
             the dossier never listed. A question about an already-VERIFIED
             skill is covered, not a gap, so it creates nothing.
        Returns the area's name, or None if the question named nothing specific."""
        if not candidate_id:
            return None
        profile = await self.db.get(PublicProfileModel, candidate_id)
        if profile is None:
            return None
        q = question.lower()
        grays = [dict(g) for g in (profile.gray_areas or [])]

        # Case 1 — a known gray area matches: bump it.
        for g in grays:
            name = str(g.get("name", ""))
            if name and any(w in q for w in _keywords(name)):
                g["companies"] = int(g.get("companies") or 0) + 1
                profile.gray_areas = grays  # reassign so SQLAlchemy sees the change
                await self.db.flush()
                return name

        # A question about an already-verified skill is covered, not a gap.
        # Match only on a skill's *distinctive* words — generic ones like
        # "cloud"/"data"/"system" overlap too many topics (e.g. a "GCP"
        # question would wrongly count as covered by ".NET & Cloud
        # Architecture" on the shared word "cloud").
        sc = await self.db.get(SearchCandidateModel, candidate_id)
        verified = list(sc.verified_skills) if sc and sc.verified_skills else []
        if any(
            any(w in q for w in _keywords(v) if w not in _GENERIC_SKILL_WORDS)
            for v in verified
        ):
            return None

        # Case 2 — discover a new gray area from the question's subject.
        topic = _extract_topic(question)
        if not topic:
            return None
        for g in grays:  # guard against a casing-only duplicate
            if str(g.get("name", "")).lower() == topic.lower():
                g["companies"] = int(g.get("companies") or 0) + 1
                profile.gray_areas = grays
                await self.db.flush()
                return str(g.get("name"))
        slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
        grays.append({"name": topic, "area_id": f"g_{slug}", "companies": 1})
        profile.gray_areas = grays
        await self.db.flush()
        return topic

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
