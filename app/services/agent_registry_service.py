"""Agent registry + execution seam.

`AgentRegistryService` manages the six pre-defined agent configs
(model binding + system message, admin-editable, Mongo-stored).

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

from app.core.exceptions import NotFoundError, ValidationError
from app.db.mongo import get_database
from app.schemas.agent_registry import AgentConfig, AgentConfigPatch, AgentRunResult

log = logging.getLogger(__name__)

# Fallback generators registered by feature modules:
#   key = agent id, value = async fn(context: dict) -> str
FallbackFn = Callable[[dict[str, Any]], Awaitable[str]]
_FALLBACKS: dict[str, FallbackFn] = {}


def register_fallback(agent_id: str, fn: FallbackFn) -> None:
    _FALLBACKS[agent_id] = fn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    doc.pop("_id", None)
    return doc


class AgentRegistryService:
    def _coll(self):
        return get_database()["agent_registry"]

    async def list_agents(self) -> list[AgentConfig]:
        docs = await self._coll().find().to_list(length=50)
        return [AgentConfig.model_validate(_strip(d)) for d in docs]

    async def get(self, agent_id: str) -> AgentConfig:
        doc = await self._coll().find_one({"id": agent_id})
        if doc is None:
            raise NotFoundError(f"Agent {agent_id} not found")
        return AgentConfig.model_validate(_strip(doc))

    async def patch(self, agent_id: str, patch: AgentConfigPatch, updated_by: str) -> AgentConfig:
        diff = patch.model_dump(exclude_unset=True)
        if "modelId" in diff and diff["modelId"] is not None:
            model = await get_database()["ai_models"].find_one({"id": diff["modelId"]})
            if model is None:
                raise ValidationError(f"modelId {diff['modelId']} does not match any AI model")
        diff["updatedAt"] = _now_iso()
        diff["updatedBy"] = updated_by
        updated = await self._coll().find_one_and_update(
            {"id": agent_id}, {"$set": diff}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"Agent {agent_id} not found")
        return AgentConfig.model_validate(_strip(updated))

    async def reset_system_message(self, agent_id: str, updated_by: str) -> AgentConfig:
        current = await self.get(agent_id)
        return await self.patch(
            agent_id,
            AgentConfigPatch(systemMessage=current.defaultSystemMessage),
            updated_by,
        )

    # ── Execution ───────────────────────────────────────────────────────

    async def _resolve_model(self, config: AgentConfig) -> Optional[dict[str, Any]]:
        """The bound model, or the first active model when unbound."""
        models = get_database()["ai_models"]
        if config.modelId:
            doc = await models.find_one({"id": config.modelId})
            if doc and doc.get("status") == "active":
                return _strip(doc)
        cursor = models.find({"status": "active"})
        docs = await cursor.to_list(length=10)
        return _strip(docs[0]) if docs else None

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
                        modelId=model.get("id"),
                    )
            except Exception:  # noqa: BLE001 — degrade, never break the feature
                log.exception("Agent %s real-run failed; falling back.", agent_id)

        return await self._fallback(agent_id, context, model_id=model.get("id") if model else None)

    async def _run_real(
        self, config: AgentConfig, model: dict[str, Any], context: dict[str, Any]
    ) -> Optional[str]:
        """Run via the ported agentic framework. Returns None when the
        framework or credentials aren't available (caller falls back)."""
        try:
            from app.agents.runner import run_single_agent  # noqa: PLC0415
        except ImportError:
            return None
        return await run_single_agent(
            system_message=config.systemMessage,
            model_doc=model,
            temperature=config.temperature,
            context=context,
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
        output = await fn(context)
        return AgentRunResult(agentId=agent_id, output=output, source="fallback", modelId=model_id)
