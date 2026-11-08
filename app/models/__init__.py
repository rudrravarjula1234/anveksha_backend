"""SQLAlchemy ORM models (Postgres/Supabase), one module per domain,
mirroring `app/schemas/`. Storage-layer only — services translate to/from
the Pydantic API contract in `app/schemas/*.py`.

IMPORTANT: every domain module must be imported below, or Alembic's
autogenerate (which imports this package to discover the schema) won't
see it.
"""

from app.models.admin_ops import (  # noqa: F401
    AdminCandidate,
    AdminCompany,
    AdminConsoleSnapshot,
    AdminDossier,
    AdminFeatureFlag,
    AdminRolePermission,
    AdminSlot,
    AdminVerifier,
    FlagDef,
    FlagGroup,
    FlagState,
    IntegrityFlag,
    PilotProgram,
    PilotStudent,
    RbacAuditEntry,
    RbacCustomRole,
    RbacRole,
)
from app.models.agent_registry import AgentConfig  # noqa: F401
from app.models.ai_model import AIModel  # noqa: F401
from app.models.approvals import (  # noqa: F401
    ActiveInterviewer,
    InterviewerApproval,
    SpecialistInvite,
)
from app.models.assessment import Assessment, AssessmentBot, Coupon  # noqa: F401
from app.models.base import Base  # noqa: F401
from app.models.bot import Bot  # noqa: F401
from app.models.candidate import (  # noqa: F401
    AppNotification,
    CandidateInsight,
    OnboardingStep,
    PublicProfile,
    SessionHistoryRow,
    SkillReport,
    SkillReportDetail,
)
from app.models.company import (  # noqa: F401
    AnonymousInterviewer,
    Billing,
    Company,
    CompanyUnlock,
    CreditRate,
    CreditTransaction,
    FollowupRequest,
    FollowupSkillOption,
    GrayFollowup,
    PipelineCard,
    SearchCandidate,
    SearchFacets,
    TeamMember,
)
from app.models.credentials import ModelCredential  # noqa: F401
from app.models.portal import (  # noqa: F401
    BookingCatalog,
    Dossier,
    DossierSession,
    LiveSessionSnapshot,
    MyInterview,
    PrivacySettings,
)
from app.models.skill import (  # noqa: F401
    InterviewerAuthority,
    SkillLedger,
    SkillLedgerRow,
)
from app.models.token_usage import TokenUsage, TokenUsageAgentId, TokenUsageModelTotals  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.verifier import (  # noqa: F401
    PendingReport,
    SessionReport,
    SuggestedGap,
    VerifierConsoleState,
    VerifierSession,
    VerifierSlot,
)
from app.models.workflow import WorkflowRun, WorkflowRunStatusCount  # noqa: F401
