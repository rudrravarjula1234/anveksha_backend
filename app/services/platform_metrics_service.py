"""Aggregates platform-wide metrics for the admin dashboard — one read
across agents, bots, models, users, token usage, and the workflow-run
ledger, folded into a single typed envelope, all via SQL aggregates
(no Python-side full-table scans).
"""


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import to_wire, utc_now
from app.models.agent_registry import AgentConfig
from app.models.ai_model import AIModel
from app.models.bot import Bot
from app.models.token_usage import TokenUsageModelTotals
from app.models.user import User, UserRole
from app.schemas.admin_metrics import (
    AgentCounts,
    BotCounts,
    ModelCounts,
    ModelTokenBreakdown,
    PlatformMetrics,
    TokenMetrics,
    UserCounts,
    WorkflowCounts,
)
from app.services import workflow_runs_service as wruns
from app.temporal.compat import TEMPORAL_AVAILABLE


class PlatformMetricsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _agents(self) -> AgentCounts:
        # agent_registry is Postgres now (see the migration plan).
        # M1: one aggregate with a conditional count instead of two queries.
        total, enabled = (
            await self.db.execute(
                select(
                    func.count(AgentConfig.id),
                    func.count(AgentConfig.id).filter(AgentConfig.enabled.is_(True)),
                )
            )
        ).one()
        return AgentCounts(total=total, enabled=enabled, disabled=total - enabled)

    async def _bots(self) -> BotCounts:
        # `bots` is Postgres now (merged with the old bots_simple — see
        # the migration plan's Stage 3). "paused" (simple-view-only
        # status) folds into "inactive" here, matching bot_service.py's
        # rich-view status mapping.
        # M1: the grouped query yields every bucket (total = sum of groups),
        # so the separate `COUNT(*)` pass is gone.
        by: dict[str, int] = {}
        rows = await self.db.execute(select(Bot.status, func.count()).group_by(Bot.status))
        for status, count in rows.all():
            by[status] = count
        total = sum(by.values())
        return BotCounts(
            total=total,
            active=by.get("active", 0),
            inactive=by.get("inactive", 0) + by.get("paused", 0),
            draft=by.get("draft", 0),
        )

    async def _models(self) -> ModelCounts:
        # M1: conditional count — total + active in one pass.
        total, active = (
            await self.db.execute(
                select(
                    func.count(AIModel.id),
                    func.count(AIModel.id).filter(AIModel.status == "active"),
                )
            )
        ).one()
        return ModelCounts(total=total, active=active, inactive=total - active)

    async def _users(self) -> UserCounts:
        # M1: one query — a scalar subquery for the users total plus FILTER
        # counts per role, instead of 1 + 4 separate COUNT round-trips.
        total, candidates, interviewers, companies, admins = (
            await self.db.execute(
                select(
                    select(func.count()).select_from(User).scalar_subquery(),
                    func.count(UserRole.role).filter(UserRole.role == "candidate"),
                    func.count(UserRole.role).filter(UserRole.role == "interviewer"),
                    func.count(UserRole.role).filter(UserRole.role == "company"),
                    func.count(UserRole.role).filter(UserRole.role == "admin"),
                )
            )
        ).one()
        return UserCounts(
            total=total,
            candidates=candidates,
            interviewers=interviewers,
            companies=companies,
            admins=admins,
        )

    async def _tokens(self) -> TokenMetrics:
        # One row per model, kept current by the `trg_token_usage_totals`
        # trigger, so this never aggregates the whole token_usage ledger.
        stmt = select(TokenUsageModelTotals).order_by(TokenUsageModelTotals.total_tokens.desc())
        rows = (await self.db.execute(stmt)).scalars().all()
        breakdown = [
            ModelTokenBreakdown(
                modelName=r.model_name,
                totalTokens=int(r.total_tokens),
                totalCostUsd=round(float(r.total_cost), 6),
                requests=int(r.requests),
            )
            for r in rows
        ]
        return TokenMetrics(
            totalRequests=sum(int(r.requests) for r in rows),
            totalInputTokens=sum(int(r.input_tokens) for r in rows),
            totalOutputTokens=sum(int(r.output_tokens) for r in rows),
            totalTokens=sum(int(r.total_tokens) for r in rows),
            totalCostUsd=round(sum(float(r.total_cost) for r in rows), 6),
            byModel=breakdown,
        )

    async def _workflows(self) -> WorkflowCounts:
        stats = await wruns.get_stats(self.db)
        return WorkflowCounts(available=bool(TEMPORAL_AVAILABLE), **stats)

    async def metrics(self) -> PlatformMetrics:
        return PlatformMetrics(
            agents=await self._agents(),
            bots=await self._bots(),
            models=await self._models(),
            users=await self._users(),
            tokens=await self._tokens(),
            workflows=await self._workflows(),
            generatedAt=to_wire(utc_now()),
        )
