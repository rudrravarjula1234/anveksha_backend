"""Aggregates platform-wide metrics for the admin dashboard.

One read across the operational collections — agents, bots, models,
users, token usage, and the workflow-run ledger — folded into a single
typed envelope. Token totals are summed in Python (not via a Mongo
aggregation pipeline) so the same code path runs against the in-memory
test stub and a real Mongo.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.db.mongo import get_database
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
    def _db(self):
        return get_database()

    async def _all(self, coll: str) -> list[dict[str, Any]]:
        return await self._db()[coll].find().to_list(length=None)

    async def _agents(self) -> AgentCounts:
        docs = await self._all("agent_registry")
        enabled = sum(1 for d in docs if d.get("enabled", True))
        return AgentCounts(total=len(docs), enabled=enabled, disabled=len(docs) - enabled)

    async def _bots(self) -> BotCounts:
        docs = await self._all("bots")
        by = defaultdict(int)
        for d in docs:
            by[d.get("status", "draft")] += 1
        return BotCounts(
            total=len(docs),
            active=by["active"],
            inactive=by["inactive"],
            draft=by["draft"],
        )

    async def _models(self) -> ModelCounts:
        docs = await self._all("ai_models")
        active = sum(1 for d in docs if d.get("status") == "active")
        return ModelCounts(total=len(docs), active=active, inactive=len(docs) - active)

    async def _users(self) -> UserCounts:
        docs = await self._all("users")

        def with_role(role: str) -> int:
            return sum(1 for d in docs if role in (d.get("roles") or []))

        return UserCounts(
            total=len(docs),
            candidates=with_role("candidate"),
            interviewers=with_role("interviewer"),
            companies=with_role("company"),
            admins=with_role("admin"),
        )

    async def _tokens(self) -> TokenMetrics:
        docs = await self._all("token_usage")
        by_model: dict[str, dict[str, float]] = defaultdict(
            lambda: {"totalTokens": 0, "totalCostUsd": 0.0, "requests": 0}
        )
        total_in = total_out = total_tok = 0
        total_cost = 0.0
        for d in docs:
            name = d.get("model_name", "unknown")
            tokens = int(d.get("total_tokens", 0) or 0)
            cost = float(d.get("total_cost", 0.0) or 0.0)
            total_in += int(d.get("input_tokens", 0) or 0)
            total_out += int(d.get("output_tokens", 0) or 0)
            total_tok += tokens
            total_cost += cost
            by_model[name]["totalTokens"] += tokens
            by_model[name]["totalCostUsd"] += cost
            by_model[name]["requests"] += 1
        breakdown = [
            ModelTokenBreakdown(
                modelName=name,
                totalTokens=int(v["totalTokens"]),
                totalCostUsd=round(v["totalCostUsd"], 6),
                requests=int(v["requests"]),
            )
            for name, v in sorted(by_model.items(), key=lambda kv: -kv[1]["totalTokens"])
        ]
        return TokenMetrics(
            totalRequests=len(docs),
            totalInputTokens=total_in,
            totalOutputTokens=total_out,
            totalTokens=total_tok,
            totalCostUsd=round(total_cost, 6),
            byModel=breakdown,
        )

    async def _workflows(self) -> WorkflowCounts:
        stats = await wruns.get_stats()
        return WorkflowCounts(available=bool(TEMPORAL_AVAILABLE), **stats)

    async def metrics(self) -> PlatformMetrics:
        return PlatformMetrics(
            agents=await self._agents(),
            bots=await self._bots(),
            models=await self._models(),
            users=await self._users(),
            tokens=await self._tokens(),
            workflows=await self._workflows(),
            generatedAt=datetime.now(timezone.utc).isoformat(),
        )
