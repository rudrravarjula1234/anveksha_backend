"""Single-shot agent execution for the agent registry.

`run_single_agent` is the bridge between the registry
(`app/services/agent_registry_service.py`) and the ported AutoGen
framework. It performs one system-message + prompt completion against
the model bound to the agent.

Returns None (instead of raising) when the framework or credentials are
unavailable so the registry can fall back gracefully.
"""

import json
import logging
from typing import Any, Optional

from app.agents.autogen_compat import AUTOGEN_AVAILABLE
from app.agents.credentials import get_credential
from app.agents.model_config_adapter import admin_model_to_config

log = logging.getLogger(__name__)


def _context_to_prompt(context: dict[str, Any]) -> str:
    """Render the structured feature context as the user prompt.

    Features pass a dict like {"task": "...", "candidateRef": "ANV-2481",
    "evidence": [...]} — we serialise it deterministically so the agent
    sees everything and the prompt is reproducible.
    """
    task = context.get("task") or "Perform your role on the data below."
    payload = {k: v for k, v in context.items() if k != "task"}
    if not payload:
        return task
    return f"{task}\n\nDATA:\n{json.dumps(payload, indent=2, ensure_ascii=False, default=str)}"


async def run_single_agent(
    *,
    system_message: str,
    model_doc: dict[str, Any],
    temperature: float,
    context: dict[str, Any],
) -> Optional[str]:
    """One-shot completion. None → caller should use its fallback."""
    if not AUTOGEN_AVAILABLE:
        return None

    config = admin_model_to_config(model_doc)
    provider_name = config.get("model_provider")
    credential = await get_credential(provider_name or "")
    if not credential or not credential.get("api_key"):
        log.info("No credential for provider %s — falling back.", provider_name)
        return None

    # Imported lazily — only reachable when AUTOGEN_AVAILABLE is True.
    from app.agents.providers.factory import ModelProviderFactory  # noqa: PLC0415

    config = {**config, "temperature": temperature}
    provider = ModelProviderFactory.create(
        model_config=config,
        api_key=credential.get("api_key"),
        endpoint=credential.get("endpoint") or config.get("model_endpoint"),
    )

    prompt = _context_to_prompt(context)
    output = await provider.direct_call(user_input=prompt, system_message=system_message)
    return output if isinstance(output, str) and output.strip() else None
