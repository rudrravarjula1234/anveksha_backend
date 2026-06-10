"""Adapter: ``ai_models`` collection (new backend) -> legacy model-config dicts.

The legacy framework loaded model configurations from a dedicated
``model_configs`` collection (see ``backend/schemas/model_config.py``). The
new backend stores admin-managed models as ``AdminModel`` documents in the
``ai_models`` collection (``app/schemas/ai_model.py``) with a different,
frontend-facing shape. This module bridges the two so the provider factory
and token-usage code keep their original contract.

Mapping (AdminModel doc -> internal config dict):

    model           -> model_name           (cache key)
    provider        -> model_provider       ("Azure OpenAI" -> "azure", ...)
    endpoint        -> model_endpoint
    status          -> is_active            (== "active")
    contextWindow   -> max_context_window
    costPer1kIn/Out -> pricing.{input,output}_tokens_per_million (x1000)

LLM parameters (temperature / max_tokens / top_p ...) have no source in the
new shape, so the legacy schema defaults are applied.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.mongo import get_database

COLLECTION = "ai_models"

# AdminModel.provider (display name) -> legacy provider key understood by
# ModelProviderFactory.
PROVIDER_MAP: Dict[str, str] = {
    "Anthropic": "anthropic",
    "OpenAI": "openai",
    "Azure OpenAI": "azure",
    "Google Vertex": "google",
    "AWS Bedrock": "bedrock",
    "Custom": "custom",
}

# Defaults mirroring legacy ModelConfigBase (backend/schemas/model_config.py).
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TOP_P = 0.95


def admin_model_to_config(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one AdminModel document to the legacy model-config dict."""
    provider_display = doc.get("provider", "")
    cost_in_per_1k = float(doc.get("costPer1kIn", 0.0) or 0.0)
    cost_out_per_1k = float(doc.get("costPer1kOut", 0.0) or 0.0)

    return {
        "model_name": doc["model"],
        "model_provider": PROVIDER_MAP.get(provider_display, provider_display.lower()),
        "model_endpoint": doc.get("endpoint") or None,
        # LLM parameters — legacy schema defaults (no source in AdminModel).
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "top_p": DEFAULT_TOP_P,
        "provider_config": {},
        # Pricing: AdminModel stores cost per 1K tokens; legacy CostCalculator
        # expects cost per 1M tokens.
        "pricing": {
            "input_tokens_per_million": cost_in_per_1k * 1000.0,
            "output_tokens_per_million": cost_out_per_1k * 1000.0,
            "currency": "USD",
        },
        "supports_function_calling": True,
        "supports_vision": False,
        "supports_streaming": True,
        "max_context_window": int(doc.get("contextWindow", 8192) or 8192),
        "description": doc.get("notes") or None,
        "is_active": doc.get("status") == "active",
        # Traceability back to the admin document.
        "display_name": doc.get("name"),
        "admin_model_id": doc.get("id"),
    }


async def get_all_model_configs_dict() -> Dict[str, Dict[str, Any]]:
    """All *active* model configs keyed by model name (for the startup cache).

    Same contract as the legacy ``model_config_service.get_all_model_configs_dict``.
    """
    db = get_database()
    docs = await db[COLLECTION].find({"status": "active"}).to_list(length=None)
    return {doc["model"]: admin_model_to_config(doc) for doc in docs if doc.get("model")}


async def get_model_config(model_name: str) -> Optional[Dict[str, Any]]:
    """Get a single active model configuration by provider-side model name."""
    db = get_database()
    doc = await db[COLLECTION].find_one({"model": model_name, "status": "active"})
    return admin_model_to_config(doc) if doc else None


async def count_active_models() -> int:
    """Number of active models in the ``ai_models`` collection."""
    db = get_database()
    return await db[COLLECTION].count_documents({"status": "active"})
