"""Verifier console schemas.

Mirrors `anveksha_ui/src/mocks/data/verifier.ts` + `verifierOps.ts`:
queue, next-session brief, pending reports, session reports (with AI
suggested gaps), governance KPIs, slots, earnings, and the verifier
profile.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

# ─── Queue ───────────────────────────────────────────────────────────────

SessionStatus = Literal["live", "scheduled", "completed"]


class VerifierStats(ReadModel):
    rating: float
    sessionCount: int
    reliability: int
    earnings: int


class VerifierSession(ReadModel):
    id: str
    rawId: str
    time: str
    date: str
    candidate: str
    candidateInitials: str
    skill: str
    duration: int
    status: SessionStatus
    tags: list[str] = Field(default_factory=list)
    depth: str = ""


class VerifierQueue(ReadModel):
    stats: VerifierStats
    live: list[VerifierSession] = Field(default_factory=list)
    upcoming: list[VerifierSession] = Field(default_factory=list)
    completed: list[VerifierSession] = Field(default_factory=list)


class NextSessionBrief(ReadModel):
    sessionId: str
    candidate: str
    skill: str
    summary: str
    prioritizedProbes: list[str] = Field(default_factory=list)
    grayRequested: list[str] = Field(default_factory=list)


# ─── Reports ─────────────────────────────────────────────────────────────

ReportVerdict = Literal["verified", "partial", "gray"]
ReportStatus = Literal["draft", "review", "published"]


class ReportSection(ReadModel):
    id: str
    title: str
    aiScore: float
    verifierScore: Optional[float] = None
    notes: str = ""
    evidence: list[str] = Field(default_factory=list)


class SessionReport(ReadModel):
    id: str
    sessionId: str
    candidateName: str
    skill: str
    verdict: ReportVerdict
    overallScore: float
    sections: list[ReportSection] = Field(default_factory=list)
    grayAreas: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    status: ReportStatus
    createdAt: str


class SuggestedGap(ReadModel):
    id: str
    text: str
    sub: str
    accepted: bool
    note: Optional[str] = None


class ReportEnvelope(ReadModel):
    report: SessionReport
    suggestedGaps: list[SuggestedGap] = Field(default_factory=list)


class PendingReportListItem(ReadModel):
    id: str
    sessionId: str
    candidate: str
    initials: str
    skill: str
    date: str
    aiScore: int


# ─── Governance ──────────────────────────────────────────────────────────


class GovernanceSignal(ReadModel):
    id: str
    name: str
    value: int
    target: int


class GovernanceRecentReport(ReadModel):
    id: str
    candidate: str
    skill: str
    date: str
    verdict: str
    score: int


class GovernanceData(ReadModel):
    reliability: int
    scoreVariance: float
    candidateRating: float
    appealRate: float
    averageReviewTimeMin: int
    monthlyEarnings: int
    signals: list[GovernanceSignal] = Field(default_factory=list)
    recentReports: list[GovernanceRecentReport] = Field(default_factory=list)


# ─── Slots ───────────────────────────────────────────────────────────────

Weekday = Literal["Mon", "Tue", "Wed", "Thu", "Fri"]


class VerifierSlot(ReadModel):
    id: str
    day: Weekday
    time: str
    duration: Literal[30, 60, 90]
    skill: str
    booked: bool = False
    candidate: Optional[str] = None


class VerifierSlotCreate(AppModel):
    day: Optional[Weekday] = None
    time: Optional[str] = None
    duration: Optional[Literal[30, 60, 90]] = None
    skill: Optional[str] = None


# ─── Earnings ────────────────────────────────────────────────────────────


class EarningMonth(ReadModel):
    id: str
    month: str
    sessions: int
    hours: float
    amount: int
    status: Literal["Paid", "Pending"]


class RateCardRow(ReadModel):
    id: str
    label: str
    value: str


class VerifierEarnings(ReadModel):
    currentMonth: str
    currentAmount: int
    currentSessions: int
    ytdAmount: int
    ytdSessions: int
    rateStandard: int
    rateAdvanced: int
    pending: int
    months: list[EarningMonth] = Field(default_factory=list)
    rateCard: list[RateCardRow] = Field(default_factory=list)


# ─── Profile ─────────────────────────────────────────────────────────────


class QualityMetric(ReadModel):
    id: str
    metric: str
    value: str


class VerifierProfile(ReadModel):
    name: str
    title: str
    yearsExperience: int
    rating: float
    sessions: int
    bio: str
    linkedin: str
    language: str
    specializations: list[str] = Field(default_factory=list)
    pendingReports: int = 0
    quality: list[QualityMetric] = Field(default_factory=list)


class VerifierProfileUpdate(AppModel):
    name: Optional[str] = None
    title: Optional[str] = None
    yearsExperience: Optional[int] = None
    bio: Optional[str] = None
    linkedin: Optional[str] = None
    language: Optional[str] = None
    specializations: Optional[list[str]] = None
