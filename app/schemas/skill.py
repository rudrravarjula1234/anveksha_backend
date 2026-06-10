"""Skill ledger schemas.

Mirrors `anveksha_ui/src/types/skill.ts` + `src/types/interviewer.ts`.
camelCase on the wire, matching the frontend mock exactly.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import ReadModel

SkillState = Literal["verified", "partial", "gray", "claimed"]
SkillDepth = Literal[
    "Beginner", "Intermediate", "Advanced", "Expert", "Claimed only", "Not tested"
]
InterviewerMode = Literal["none", "pending", "freelance", "specialist"]
InterviewerOrigin = Literal["bot-discovered", "self-requested", "admin-invited"]


class InterviewerAuthority(ReadModel):
    skillId: str
    skillName: str
    approvedAt: str


class InterviewerStats(ReadModel):
    sessions: Optional[int] = None
    rating: Optional[float] = None
    reliability: Optional[int] = None
    peerScore: Optional[int] = None
    appealRate: Optional[float] = None
    averageReviewMinutes: Optional[int] = None
    # Absent for specialists / company-internal — the UI hides the
    # earnings widget when this is missing.
    monthlyEarnings: Optional[int] = None


class ExternalProof(ReadModel):
    id: str
    label: str
    url: str


class InterviewerStatus(ReadModel):
    mode: InterviewerMode = "none"
    origin: Optional[InterviewerOrigin] = None
    approvedBy: Optional[str] = None
    approvedAt: Optional[str] = None
    authorities: list[InterviewerAuthority] = Field(default_factory=list)
    stats: Optional[InterviewerStats] = None
    bio: Optional[str] = None
    externalProof: Optional[list[ExternalProof]] = None


class SkillLedgerRow(ReadModel):
    id: str
    name: str
    state: SkillState
    depth: SkillDepth
    score: Optional[float] = None
    lastVerified: Optional[str] = None
    sessions: int = 0
    reportId: Optional[str] = None
    authority: Optional[bool] = None
    authoritySince: Optional[str] = None


class SkillLedger(ReadModel):
    candidateId: str
    candidateName: str
    candidateTitle: str
    candidateLocation: str
    candidateInitials: str
    dossierId: str
    verificationScore: float = 0
    verifiedCount: int = 0
    partialCount: int = 0
    grayCount: int = 0
    topPercent: int = 0
    interviewerStatus: InterviewerStatus
    skills: list[SkillLedgerRow] = Field(default_factory=list)
