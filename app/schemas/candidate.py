"""Candidate-portal schemas.

Mirrors `anveksha_ui/src/mocks/data/candidateExtras.ts`,
`skillReportDetails.ts`, `notifications.ts` and the `/api/profiles/me`
shape from `handlers/profiles.ts`.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

# ─── Skill reports (list + detail) ───────────────────────────────────────


class SkillReport(ReadModel):
    id: str
    skill: str
    verifier: str
    score: int
    date: str
    status: Literal["published", "in-review", "draft"]
    companiesViewed: int


class ReportParty(ReadModel):
    name: str
    id: str


class ReportVerifier(ReadModel):
    name: str
    id: str
    title: str
    rating: str


class FitSignal(ReadModel):
    area: str
    signal: str
    color: str


class RubricRow(ReadModel):
    id: str
    dim: str
    score: int


class ReportPhase(ReadModel):
    num: str
    title: str
    done: bool
    summary: str


class ReportGap(ReadModel):
    id: str
    area: str
    evidence: str
    severity: Literal["low", "medium", "high"]


class ReportGrayItem(ReadModel):
    id: str
    area: str
    companies: int


class ReportEvidence(ReadModel):
    id: str
    t: str
    type: Literal["claim", "hesitation", "insight"]
    speaker: str
    text: str
    verdict: str
    verdictColor: str


class SkillReportDetail(ReadModel):
    id: str
    skillId: str
    assessmentTitle: str
    candidate: ReportParty
    verifier: ReportVerifier
    date: str
    duration: str
    type: Literal["live", "bot", "bot-assisted"]
    score: int
    depth: str
    verdict: str
    verdictLong: str
    fitSignals: list[FitSignal] = Field(default_factory=list)
    rubric: list[RubricRow] = Field(default_factory=list)
    phases: list[ReportPhase] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    gaps: list[ReportGap] = Field(default_factory=list)
    gray: list[ReportGrayItem] = Field(default_factory=list)
    evidence: list[ReportEvidence] = Field(default_factory=list)


# ─── Insights ────────────────────────────────────────────────────────────


class CandidateInsight(ReadModel):
    id: str
    kind: Literal["follow-up", "gap", "momentum", "integrity"]
    title: str
    body: str
    cta: str
    companies: Optional[int] = None
    acted: bool = False


# ─── Onboarding ──────────────────────────────────────────────────────────


class OnboardingStep(ReadModel):
    id: str
    title: str
    body: str
    done: bool


# ─── Public profile ──────────────────────────────────────────────────────


class ProfileHighlight(ReadModel):
    id: str
    skill: str
    score: int


class ConstellationSkill(ReadModel):
    name: str
    score: int
    state: Literal["verified", "partial", "gray"]


class TimelineEntry(ReadModel):
    id: str
    date: str
    skill: str
    score: int
    type: Literal["live", "bot", "bot-assisted"]
    note: Optional[str] = None


class GrayArea(ReadModel):
    id: str
    name: str
    companies: int


class PublicProfileData(ReadModel):
    shareUrl: str
    anvId: str
    lastUpdated: str
    headline: str
    views: int
    uniqueCompanies: int
    inboundChats: int
    about: str
    highlights: list[ProfileHighlight] = Field(default_factory=list)
    constellation: list[ConstellationSkill] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    grayAreas: list[GrayArea] = Field(default_factory=list)


# ─── Session history ─────────────────────────────────────────────────────


class SessionHistoryRow(ReadModel):
    id: str
    skill: str
    date: str
    duration: str
    verifier: str
    score: int
    status: Literal["published", "archived", "in-review"]
    note: Optional[str] = None


# ─── Notifications ───────────────────────────────────────────────────────


class AppNotification(ReadModel):
    id: str
    kind: Literal["session", "dossier", "company", "followup", "integrity"]
    title: str
    body: str
    createdAt: str
    read: bool = False
    href: Optional[str] = None


# ─── /api/profiles/me ────────────────────────────────────────────────────


class UserProfileMe(ReadModel):
    id: str
    user_id: str
    skills: list[str] = Field(default_factory=list)
    experience_years: int = 0
    current_role: str = ""
    bio: str = ""
    location: str = ""
    candidate_rating: float = 0
    interviews_taken: int = 0
    average_score: float = 0
    shared_report_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class UserProfilePatch(AppModel):
    """PATCH /api/profiles/me — free-form profile edits."""

    bio: Optional[str] = None
    location: Optional[str] = None
    current_role: Optional[str] = None
    experience_years: Optional[int] = None
    skills: Optional[list[str]] = None
