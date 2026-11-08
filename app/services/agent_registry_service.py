"""Agent registry + execution seam.

`AgentRegistryService` manages the six pre-defined agent configs
(model binding + system message, admin-editable, Postgres-stored).

`run_agent()` is the single execution entrypoint every feature calls
(brief generation, report drafting, gap/gray analysis, search, chat).
Resolution order:

1. Load the agent's config (enabled? which model? which system message?).
2. If the ported agentic framework (app.agents) is importable AND a
   provider credential exists for the bound model → run the real agent.
3. Otherwise → call the registered deterministic fallback so the product
   stays fully functional without any LLM keys.

The result envelope says which path produced the text (`source`), so the
UI can badge AI output appropriately.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.timefmt import to_wire
from app.models.agent_registry import AgentConfig as AgentConfigModel
from app.models.ai_model import AIModel
from app.repositories.agent_registry_repo import AgentRegistryRepository
from app.repositories.ai_model_repo import AIModelRepository
from app.schemas.agent_registry import AgentConfig, AgentConfigPatch, AgentRunResult

log = logging.getLogger(__name__)

# Fallback generators registered by feature modules:
#   key = agent id, value = async fn(context: dict, db: AsyncSession) -> str
# `db` is this service's own session — fallbacks needing Postgres reads
# must use it, not a new connection, or they won't see uncommitted work
# (matters most in tests, where a request runs inside one rolled-back
# transaction).
FallbackFn = Callable[[dict[str, Any], AsyncSession], Awaitable[str]]
_FALLBACKS: dict[str, FallbackFn] = {}


def register_fallback(agent_id: str, fn: FallbackFn) -> None:
    _FALLBACKS[agent_id] = fn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(row: AgentConfigModel) -> AgentConfig:
    return AgentConfig(
        id=row.id,
        name=row.name,
        description=row.description,
        usedBy=list(row.used_by or []),
        modelId=row.model_id,
        systemMessage=row.system_message,
        defaultSystemMessage=row.default_system_message,
        temperature=row.temperature,
        enabled=row.enabled,
        updatedAt=to_wire(row.updated_at),
        updatedBy=row.updated_by,
    )


class AgentRegistryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AgentRegistryRepository(db)
        self.models_repo = AIModelRepository(db)

    async def list_agents(self) -> list[AgentConfig]:
        rows = await self.repo.list_all()
        return [_to_schema(r) for r in rows]

    async def get(self, agent_id: str) -> AgentConfig:
        row = await self.repo.find_by_id(agent_id)
        if row is None:
            raise NotFoundError(f"Agent {agent_id} not found")
        return _to_schema(row)

    async def patch(self, agent_id: str, patch: AgentConfigPatch, updated_by: str) -> AgentConfig:
        diff = patch.model_dump(exclude_unset=True)
        if "modelId" in diff and diff["modelId"] is not None:
            model = await self.models_repo.find_by_id(diff["modelId"])
            if model is None:
                raise ValidationError(f"modelId {diff['modelId']} does not match any AI model")
        field_map = {
            "modelId": "model_id",
            "systemMessage": "system_message",
            "temperature": "temperature",
            "enabled": "enabled",
        }
        kwargs = {field_map[k]: v for k, v in diff.items() if k in field_map}
        kwargs["updated_by"] = updated_by
        row = await self.repo.update_by_id(agent_id, **kwargs)
        if row is None:
            raise NotFoundError(f"Agent {agent_id} not found")
        return _to_schema(row)

    async def reset_system_message(self, agent_id: str, updated_by: str) -> AgentConfig:
        current = await self.get(agent_id)
        return await self.patch(
            agent_id,
            AgentConfigPatch(systemMessage=current.defaultSystemMessage),
            updated_by,
        )

    # ── Execution ───────────────────────────────────────────────────────

    async def _resolve_model(self, config: AgentConfig) -> Optional[AIModel]:
        """The bound model, or the first active model when unbound."""
        if config.modelId:
            model = await self.models_repo.find_by_id(config.modelId)
            if model is not None and model.status == "active":
                return model
        stmt = select(AIModel).where(AIModel.status == "active").order_by(AIModel.id).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def run_agent(self, agent_id: str, context: dict[str, Any]) -> AgentRunResult:
        config = await self.get(agent_id)
        if not config.enabled:
            return await self._fallback(agent_id, context, model_id=None)

        model = await self._resolve_model(config)

        # Try the real framework when it's importable + a credential exists.
        if model is not None:
            try:
                output = await self._run_real(config, model, context)
                if output is not None:
                    return AgentRunResult(
                        agentId=agent_id,
                        output=output,
                        source="agent",
                        modelId=model.id,
                    )
            except Exception:  # noqa: BLE001 — degrade, never break the feature
                log.exception("Agent %s real-run failed; falling back.", agent_id)

        return await self._fallback(agent_id, context, model_id=model.id if model else None)

    async def _run_real(
        self, config: AgentConfig, model: AIModel, context: dict[str, Any]
    ) -> Optional[str]:
        """Run via the ported agentic framework. Returns None when the
        framework or credentials aren't available (caller falls back)."""
        try:
            from app.agents.runner import run_single_agent  # noqa: PLC0415
        except ImportError:
            return None
        return await run_single_agent(
            system_message=config.systemMessage,
            model=model,
            temperature=config.temperature,
            context=context,
            db=self.db,
        )

    async def _fallback(
        self, agent_id: str, context: dict[str, Any], model_id: Optional[str]
    ) -> AgentRunResult:
        fn = _FALLBACKS.get(agent_id)
        if fn is None:
            raise ValidationError(
                f"Agent {agent_id} unavailable and no fallback registered",
                status_code=503,
            )
        output = await fn(context, self.db)
        return AgentRunResult(agentId=agent_id, output=output, source="fallback", modelId=model_id)
