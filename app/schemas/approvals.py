"""Interviewer-approval schemas — mirror of anveksha_ui/src/types/approvals.ts."""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel
from app.schemas.skill import ExternalProof

ApprovalStatus = Literal["pending", "approved", "rejected"]
ApprovalOrigin = Literal["bot-discovered", "self-requested"]


class InterviewerApproval(ReadModel):
    id: str
    candidateId: str
    candidateName: str
    candidateInitials: str
    dossierId: str
    requestedSkill: str
    origin: ApprovalOrigin
    submittedAt: str
    status: ApprovalStatus
    candidateScore: Optional[float] = None
    candidateSessions: Optional[int] = None
    botReasoning: Optional[str] = None
    reviewedBy: Optional[str] = None
    reviewedAt: Optional[str] = None
    decisionNote: Optional[str] = None


class SpecialistInvite(ReadModel):
    id: str
    email: str
    firstName: str
    lastName: str
    skillName: str
    bio: str = ""
    externalProof: list[ExternalProof] = Field(default_factory=list)
    status: Literal["sent", "accepted", "expired"]
    invitedAt: str
    invitedBy: str
    acceptedAt: Optional[str] = None


class ActiveInterviewer(ReadModel):
    candidateId: str
    candidateName: str
    candidateInitials: str
    mode: Literal["freelance", "specialist"]
    authorities: list[str] = Field(default_factory=list)
    sessions: int = 0
    rating: Optional[float] = None
    reliability: Optional[int] = None
    joinedAt: str


class ApprovalsOverview(ReadModel):
    approvals: list[InterviewerApproval] = Field(default_factory=list)
    invites: list[SpecialistInvite] = Field(default_factory=list)
    active: list[ActiveInterviewer] = Field(default_factory=list)


class DecisionBody(AppModel):
    note: Optional[str] = None


class SelfRequestBody(AppModel):
    skillName: str = Field(min_length=1)
    skillScore: Optional[float] = None
    sessions: Optional[int] = None


class SpecialistInviteBody(AppModel):
    email: str = Field(min_length=3)
    firstName: str = Field(min_length=1)
    lastName: str = Field(min_length=1)
    skillName: str = Field(min_length=1)
    bio: str = ""
    externalProof: list[ExternalProof] = Field(default_factory=list)
