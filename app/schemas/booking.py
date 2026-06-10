"""Booking + live-session + dossier schemas.

Mirrors `bookingCatalog`, `liveSessionSnapshot` and `candidateDossier`
from anveksha_ui/src/mocks/data/candidate.ts.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel
from app.schemas.skill import SkillLedger

# ─── Booking catalog ─────────────────────────────────────────────────────


class BookingDay(ReadModel):
    id: str
    day: str
    date: str
    status: Literal["avail", "full"]
    slotCount: int


class BookingSlot(ReadModel):
    id: str
    time: str
    verifier: str
    rating: float
    duration: int


class BookingCatalog(ReadModel):
    catalogId: str
    skillName: str
    description: str
    depth: str
    duration: int
    style: str
    format: str
    evidence: str
    probes: str
    weekRange: str
    days: list[BookingDay] = Field(default_factory=list)
    slotsByDay: dict[str, list[BookingSlot]] = Field(default_factory=dict)


class ScheduleRequest(AppModel):
    dayId: str
    slotId: str


class ScheduleResponse(ReadModel):
    id: str
    status: str
    scheduled_date: str
    dayId: str
    slotId: str
    catalog: BookingCatalog


class MyInterview(ReadModel):
    id: str
    catalog_id: str
    title: str
    status: str
    scheduled_date: str


# ─── Live session ────────────────────────────────────────────────────────


class SessionParty(ReadModel):
    name: str
    initials: str
    color: str


class TranscriptLine(ReadModel):
    t: str
    who: str
    text: str


class SessionPhase(ReadModel):
    num: str
    title: str
    done: bool
    active: bool


class AssessmentSignal(ReadModel):
    label: str
    value: int
    tag: Literal["strong", "solid", "partial", "unexplored"]


class UnverifiedClaim(ReadModel):
    text: str
    at: str


class LiveSessionSnapshot(ReadModel):
    id: str
    catalogId: str
    skill: str
    status: Literal["live", "ended"]
    elapsedSeconds: int
    candidate: SessionParty
    verifier: SessionParty
    transcript: list[TranscriptLine] = Field(default_factory=list)
    phases: list[SessionPhase] = Field(default_factory=list)
    currentProbe: str = ""
    assessment: list[AssessmentSignal] = Field(default_factory=list)
    suggestedProbes: list[str] = Field(default_factory=list)
    unverifiedClaim: Optional[UnverifiedClaim] = None


# ─── Dossier ─────────────────────────────────────────────────────────────


class DossierSession(ReadModel):
    id: str
    date: str
    skill: str
    verifier: str
    score: int
    duration: int
    verdict: str


class Dossier(ReadModel):
    id: str
    candidateId: str
    candidateName: str
    candidateInitials: str
    candidateTitle: str
    candidateLocation: str
    years: int
    verificationScore: float
    ledger: SkillLedger
    sessions: list[DossierSession] = Field(default_factory=list)
    grayAreas: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    isShared: bool = False
