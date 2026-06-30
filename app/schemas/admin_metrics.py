"""Response contract for the admin platform dashboard.

camelCase on the wire (see app/schemas/base.py) so the TypeScript types
in the frontend match byte-for-byte.
"""

from app.schemas.base import ReadModel


class AgentCounts(ReadModel):
    total: int
    enabled: int
    disabled: int


class BotCounts(ReadModel):
    total: int
    active: int
    inactive: int
    draft: int


class ModelCounts(ReadModel):
    total: int
    active: int
    inactive: int


class UserCounts(ReadModel):
    """Per-role membership. Roles overlap (an interviewer is also a
    candidate), so these do NOT sum to `total` — `total` is distinct users."""

    total: int
    candidates: int
    interviewers: int
    companies: int
    admins: int


class ModelTokenBreakdown(ReadModel):
    modelName: str
    totalTokens: int
    totalCostUsd: float
    requests: int


class TokenMetrics(ReadModel):
    totalRequests: int
    totalInputTokens: int
    totalOutputTokens: int
    totalTokens: int
    totalCostUsd: float
    byModel: list[ModelTokenBreakdown]


class WorkflowCounts(ReadModel):
    """Counts from the `workflow_runs` ledger. `available` reflects whether
    the Temporal SDK is installed (i.e. new runs can actually be started)."""

    available: bool
    total: int
    running: int
    completed: int
    failed: int


class PlatformMetrics(ReadModel):
    agents: AgentCounts
    bots: BotCounts
    models: ModelCounts
    users: UserCounts
    tokens: TokenMetrics
    workflows: WorkflowCounts
    generatedAt: str
