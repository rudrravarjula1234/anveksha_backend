"""Assessment + coupon schemas.

Mirrors `anveksha_ui/src/mocks/data/assessmentsFull.ts` (AssessmentFull,
CouponCode), `adminWorkflow.ts` (AdminAssessment — the slim admin list)
and `coupons.ts` (Coupon — admin-managed, with `active`).

One storage shape (AssessmentFull) backs every view; the slim admin list
and the candidate catalog are projections.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

AssessmentType = Literal["live", "bot", "bot-assisted"]
# Union of the slim + full domain/depth vocabularies so either UI writes.
AssessmentDomain = Literal[
    "Backend", "Frontend", "Data", "Payments", "Cloud", "Platform", "Leadership", "Behavioral"
]
AssessmentDepth = Literal["Foundational", "Intermediate", "Advanced", "Expert", "Staff"]


class AssessmentFull(ReadModel):
    id: str
    slug: str
    title: str
    domain: AssessmentDomain
    depth: AssessmentDepth
    type: AssessmentType
    duration: int = 60
    price: int = 0
    available: int = 4
    popular: bool = False
    published: bool = False
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    probes: list[str] = Field(default_factory=list)
    botIds: list[str] = Field(default_factory=list)
    sessions: int = 0


class AssessmentFullCreate(AppModel):
    """POST body — every field optional; the mock fills generous defaults."""

    slug: Optional[str] = None
    title: Optional[str] = None
    domain: Optional[AssessmentDomain] = None
    depth: Optional[AssessmentDepth] = None
    type: Optional[AssessmentType] = None
    duration: Optional[int] = Field(default=None, ge=1)
    price: Optional[int] = Field(default=None, ge=0)
    available: Optional[int] = Field(default=None, ge=0)
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    probes: Optional[list[str]] = None
    botIds: Optional[list[str]] = None


class AssessmentFullUpdate(AppModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    domain: Optional[AssessmentDomain] = None
    depth: Optional[AssessmentDepth] = None
    type: Optional[AssessmentType] = None
    duration: Optional[int] = Field(default=None, ge=1)
    price: Optional[int] = Field(default=None, ge=0)
    available: Optional[int] = Field(default=None, ge=0)
    popular: Optional[bool] = None
    published: Optional[bool] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    probes: Optional[list[str]] = None
    botIds: Optional[list[str]] = None


class AdminAssessment(ReadModel):
    """Slim admin list — projection of AssessmentFull."""

    id: str
    slug: str
    title: str
    domain: AssessmentDomain
    depth: AssessmentDepth
    type: AssessmentType
    duration: int
    price: int
    published: bool
    sessions: int


class CatalogAssessment(ReadModel):
    """Candidate-facing catalog row — published assessments only."""

    id: str
    slug: str
    title: str
    domain: AssessmentDomain
    depth: AssessmentDepth
    type: AssessmentType
    price: int
    duration: int
    available: int
    popular: bool
    tags: list[str] = Field(default_factory=list)


# ─── Coupons ─────────────────────────────────────────────────────────────

CouponType = Literal["percent", "fixed"]


class Coupon(ReadModel):
    """Admin-managed coupon (includes active flag)."""

    code: str
    type: CouponType
    value: int
    desc: str = ""
    active: bool = True


class CouponCreate(AppModel):
    code: str = Field(min_length=2, max_length=40)
    type: CouponType
    value: int = Field(ge=0)
    desc: str = ""


class CouponCode(ReadModel):
    """Candidate-facing coupon shape — no active flag (only active ones ship)."""

    code: str
    type: CouponType
    value: int
    desc: str = ""
