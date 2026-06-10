"""Admin ops schemas.

Mirrors the admin mock contracts across three frontend handler files:

- `anveksha_ui/src/mocks/handlers/admin.ts`         (dashboard, users,
  simple bots, simple feature flags, permissions, simple pilots)
- `anveksha_ui/src/mocks/handlers/adminWorkflow.ts` (overview, dossiers,
  slots, verifiers, candidates, companies, integrity, analytics)
- `anveksha_ui/src/mocks/handlers/adminRich.ts`     (flag registry+state,
  RBAC, pilots-full, pilot students)

Field names are camelCase or snake_case exactly as the mock uses them
(`AdminUser` is snake_case — it mirrors the users table; everything
else is camelCase).
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel
from app.schemas.user import UserRole

# ─── Dashboard ───────────────────────────────────────────────────────────


class AdminDashboard(ReadModel):
    totalUsers: int
    activeCandidates: int
    activeVerifiers: int
    activeCompanies: int
    sessionsToday: int
    reportsThisWeek: int


# ─── Users ───────────────────────────────────────────────────────────────


class AdminUser(ReadModel):
    id: str
    email: str
    name: str
    roles: list[UserRole] = Field(default_factory=list)
    is_active: bool = True
    created_at: str
    last_login: Optional[str] = None


class UserRolesUpdate(AppModel):
    roles: list[UserRole]


# ─── Bots (simple shape — src/types/admin.ts Bot, NOT BotFull) ──────────

BotType = Literal["interviewer", "reviewer", "co-pilot"]
BotStatus = Literal["active", "paused", "draft"]


class Bot(ReadModel):
    id: str
    name: str
    description: str = ""
    type: BotType
    model: str
    status: BotStatus
    sessionsRun: int = 0
    avgRating: float = 0
    createdAt: str


class BotCreate(AppModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[BotType] = None
    model: Optional[str] = None


# ─── Feature flags (simple list — admin.ts) ─────────────────────────────

FlagScope = Literal["global", "candidate", "verifier", "company"]


class FeatureFlag(ReadModel):
    key: str
    name: str
    description: str = ""
    enabled: bool
    scope: FlagScope


class FeatureFlagUpdate(AppModel):
    enabled: bool


# ─── Role permissions (simple list — admin.ts) ──────────────────────────


class RolePermission(ReadModel):
    role: str
    permissions: list[str] = Field(default_factory=list)


# ─── Pilots ──────────────────────────────────────────────────────────────

PilotStatus = Literal["active", "draft", "completed"]


class PilotProgramSimple(ReadModel):
    """The admin.ts shape — the full record minus `dept`/`assessments`."""

    id: str
    name: str
    college: str
    batch: str
    coordinator: str
    students: int
    completed: int
    avgScore: int
    status: PilotStatus
    startDate: str
    endDate: str


class PilotProgram(PilotProgramSimple):
    """The pilotsFull.ts shape."""

    dept: str
    assessments: list[str] = Field(default_factory=list)


class PilotProgramCreate(AppModel):
    name: Optional[str] = None
    college: Optional[str] = None
    dept: Optional[str] = None
    batch: Optional[str] = None
    coordinator: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    assessments: Optional[list[str]] = None


class PilotStudent(ReadModel):
    id: str
    name: str
    email: str
    program: str
    completed: int = 0
    pending: int = 0
    avgScore: int = 0
    status: Literal["active", "registered"]


class PilotStudentCreate(AppModel):
    name: str
    email: str
    program: str


class PilotStudentImportRequest(AppModel):
    rows: list[PilotStudentCreate] = Field(default_factory=list)


# ─── Overview ────────────────────────────────────────────────────────────

ActivityTone = Literal["oxblood", "verdant", "ochre", "sky", "ink"]


class OverviewStat(ReadModel):
    label: str
    value: int
    sub: str = ""
    color: Optional[str] = None


class AdminActivity(ReadModel):
    id: str
    text: str
    time: str
    tone: ActivityTone


class AdminOverview(ReadModel):
    stats: list[OverviewStat] = Field(default_factory=list)
    activity: list[AdminActivity] = Field(default_factory=list)


# ─── Dossiers ────────────────────────────────────────────────────────────

DossierStatus = Literal["published", "in-review", "draft", "archived"]


class AdminDossier(ReadModel):
    id: str
    candidate: str
    skill: str
    verifier: str
    date: str
    score: int
    status: DossierStatus


class DossierCreate(AppModel):
    candidate: Optional[str] = None
    skill: Optional[str] = None
    verifier: Optional[str] = None
    date: Optional[str] = None
    score: Optional[int] = None
    status: Optional[DossierStatus] = None


class DossierPatch(AppModel):
    candidate: Optional[str] = None
    skill: Optional[str] = None
    verifier: Optional[str] = None
    date: Optional[str] = None
    score: Optional[int] = None
    status: Optional[DossierStatus] = None


# ─── Slots (admin view — includes the verifier column) ──────────────────


class AdminSlot(ReadModel):
    id: str
    verifier: str
    day: str
    time: str
    duration: int
    skill: str
    booked: bool = False
    candidate: Optional[str] = None


class AdminSlotCreate(AppModel):
    verifier: Optional[str] = None
    day: Optional[str] = None
    time: Optional[str] = None
    duration: Optional[int] = None
    skill: Optional[str] = None


# ─── Verifiers (admin roster) ────────────────────────────────────────────

VerifierQuality = Literal["Exemplary", "Strong", "Probation"]
VerifierTier = Literal["active", "applicants", "probation"]


class AdminVerifier(ReadModel):
    id: str
    name: str
    specialization: str
    sessions: int
    rating: float
    quality: VerifierQuality
    since: str
    tier: VerifierTier
    experience: Optional[str] = None
    applied: Optional[str] = None
    sample: Optional[Literal["Reviewed", "Pending"]] = None


class VerifierInviteRequest(AppModel):
    email: str
    specialization: str


# ─── Candidates (admin view) ─────────────────────────────────────────────


class AdminCandidate(ReadModel):
    id: str
    name: str
    location: str
    verifications: int
    topScore: int
    lastSession: str
    status: Literal["active", "blacklisted"]


# ─── Companies (admin view) ──────────────────────────────────────────────


class AdminCompany(ReadModel):
    id: str
    name: str
    plan: Literal["Starter", "Growth", "Enterprise"]
    seats: int
    seatsUsed: int
    chats: int
    followups: int
    since: str
    status: Literal["active", "trial", "churned"]


# ─── Integrity ───────────────────────────────────────────────────────────

Severity = Literal["high", "medium", "confirmed"]


class IntegrityFlag(ReadModel):
    id: str
    summary: str
    refId: str
    severity: Severity
    date: str
    action: str


class IntegritySignal(ReadModel):
    id: str
    name: str
    status: str


class IntegrityEnvelope(ReadModel):
    flags: list[IntegrityFlag] = Field(default_factory=list)
    signals: list[IntegritySignal] = Field(default_factory=list)


# ─── Analytics ───────────────────────────────────────────────────────────


class AnalyticsTopStat(ReadModel):
    label: str
    value: str
    color: Optional[str] = None
    sub: Optional[str] = None


class AnalyticsSkill(ReadModel):
    name: str
    share: int


class AnalyticsData(ReadModel):
    topStats: list[AnalyticsTopStat] = Field(default_factory=list)
    months: list[str] = Field(default_factory=list)
    sessions: list[int] = Field(default_factory=list)
    topSkills: list[AnalyticsSkill] = Field(default_factory=list)


# ─── Feature flags (rich registry + state — adminRich.ts) ───────────────


class FlagDef(ReadModel):
    id: str
    label: str
    desc: str = ""
    default: bool


class FlagGroup(ReadModel):
    group: str
    flags: list[FlagDef] = Field(default_factory=list)


class FlagsEnvelope(ReadModel):
    registry: list[FlagGroup] = Field(default_factory=list)
    state: dict[str, bool] = Field(default_factory=dict)


class FlagsStateResponse(ReadModel):
    ok: bool
    state: dict[str, bool] = Field(default_factory=dict)


class FlagGroupToggle(AppModel):
    value: bool


# ─── RBAC (rich — adminRich.ts) ──────────────────────────────────────────

RbacRoleId = Literal["candidate", "verifier", "company", "admin"]


class PermissionDef(ReadModel):
    id: str
    label: str
    on: bool
    locked: bool


class RoleDef(ReadModel):
    id: RbacRoleId
    label: str
    color: str
    perms: list[PermissionDef] = Field(default_factory=list)


class CustomRole(ReadModel):
    id: str
    name: str
    baseRole: RbacRoleId
    desc: str = ""
    members: int = 0
    overrides: dict[str, bool] = Field(default_factory=dict)


class CustomRoleCreate(AppModel):
    name: Optional[str] = None
    baseRole: Optional[RbacRoleId] = None
    desc: Optional[str] = None
    overrides: Optional[dict[str, bool]] = None


class AuditLogEntry(ReadModel):
    id: str
    time: str
    actor: str
    action: str
    detail: str


class RbacEnvelope(ReadModel):
    roles: list[RoleDef] = Field(default_factory=list)
    customRoles: list[CustomRole] = Field(default_factory=list)
    audit: list[AuditLogEntry] = Field(default_factory=list)


class RbacPermUpdate(AppModel):
    on: bool
