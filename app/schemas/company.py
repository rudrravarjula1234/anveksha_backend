"""Company-portal schemas.

Mirrors anveksha_ui/src/types/company.ts plus companyOps.ts (team,
billing), followups.ts (gray follow-up tracking) and company.ts
(search + pipeline).
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

# ─── Company + anonymous interviewers ────────────────────────────────────


class CompanyProfile(ReadModel):
    id: str
    name: str
    primaryDomain: str


class AnonymousInterviewer(ReadModel):
    id: str
    displayName: str
    title: str
    email: str
    specialties: list[str] = Field(default_factory=list)
    verified: bool = False
    sessions: int = 0
    externalSessions: int = 0
    rating: Optional[float] = None
    addedAt: str


class AnonymousInterviewerCreate(AppModel):
    displayName: str = Field(min_length=1)
    title: str = Field(min_length=1)
    email: str = Field(min_length=3)
    specialties: list[str] = Field(default_factory=list)


# ─── Credits ─────────────────────────────────────────────────────────────


class CreditTransaction(ReadModel):
    id: str
    at: str
    kind: Literal["earned", "spent"]
    amount: int
    reason: str
    balanceAfter: int
    interviewerId: Optional[str] = None


class CompanyCredits(ReadModel):
    balance: int
    earnedThisMonth: int
    spentThisMonth: int
    ledger: list[CreditTransaction] = Field(default_factory=list)


class CreditMutation(AppModel):
    amount: int = Field(ge=1)
    reason: str = Field(min_length=1)
    interviewerId: Optional[str] = None


class CreditRate(ReadModel):
    rupeesPerCredit: float
    updatedAt: str
    updatedBy: str


class CreditRatePatch(AppModel):
    rupeesPerCredit: float = Field(gt=0)


# ─── Team & billing ──────────────────────────────────────────────────────

TeamRole = Literal["Hiring Manager", "Recruiter", "Viewer"]


class TeamMember(ReadModel):
    id: str
    name: str
    email: str
    role: TeamRole
    pipelines: int = 0
    lastActive: str = ""
    status: Literal["active", "inactive"] = "active"


class TeamInvite(AppModel):
    email: str = Field(min_length=3)
    role: TeamRole


class BillingSummary(ReadModel):
    plan: Literal["Starter", "Growth", "Enterprise"]
    seats: int
    seatsUsed: int
    monthlyAmount: int
    nextBilling: str
    includes: list[str] = Field(default_factory=list)
    aiChatsUsed: int
    aiChatsIncluded: int


class Invoice(ReadModel):
    id: str
    month: str
    amount: int
    status: Literal["Paid", "Pending", "Failed"]
    pdfUrl: str


class BillingResponse(ReadModel):
    summary: BillingSummary
    invoices: list[Invoice] = Field(default_factory=list)


# ─── Gray follow-ups ─────────────────────────────────────────────────────

FollowupStatus = Literal["pending", "requested", "accepted", "completed", "declined"]


class FollowupTracking(ReadModel):
    id: str
    candidate: str
    candidateId: str
    grayArea: str
    asked: int
    requested: str
    status: FollowupStatus
    companies: Optional[str] = None
    scheduled: Optional[str] = None
    score: Optional[int] = None


# ─── Discovery / pipeline / chat ─────────────────────────────────────────


class CandidateMatch(ReadModel):
    id: str
    name: str
    initials: str
    title: str
    years: int
    location: str
    verificationScore: int
    matchPercent: int
    verifiedSkills: list[str] = Field(default_factory=list)
    graySkills: list[str] = Field(default_factory=list)
    lastActivity: str
    # PHI gating — present (true) while the company hasn't paid to
    # unlock this candidate; name/initials/location are masked then.
    locked: Optional[bool] = None
    alias: Optional[str] = None


class SearchFacet(ReadModel):
    name: str
    count: int


class SearchFacets(ReadModel):
    skills: list[SearchFacet] = Field(default_factory=list)
    locations: list[SearchFacet] = Field(default_factory=list)


class SearchRequest(AppModel):
    query: str
    filters: Optional[dict] = None


class SearchResponse(ReadModel):
    query: str
    candidates: list[CandidateMatch] = Field(default_factory=list)
    facets: SearchFacets


class PipelineCard(ReadModel):
    candidateId: str
    name: str
    initials: str
    matchPercent: int
    lastActivity: str
    stage: Literal["investigating", "followup", "shortlist", "offered"]
    note: Optional[str] = None


class PipelineBoard(ReadModel):
    investigating: list[PipelineCard] = Field(default_factory=list)
    followup: list[PipelineCard] = Field(default_factory=list)
    shortlist: list[PipelineCard] = Field(default_factory=list)
    offered: list[PipelineCard] = Field(default_factory=list)


class PipelineMove(AppModel):
    stage: Literal["investigating", "followup", "shortlist", "offered"]


class FollowupSkillOption(ReadModel):
    id: str
    name: str
    requested: int


class FollowupRequest(AppModel):
    candidateId: str
    skills: list[str] = Field(default_factory=list)
    message: str = ""


class ChatRequest(AppModel):
    candidateId: str
    prompt: str
