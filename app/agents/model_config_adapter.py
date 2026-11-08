"""Adapter: ``ai_models`` table rows -> the model-config dict shape the
provider factory and token-usage code expect. LLM parameters (temperature,
max_tokens, top_p) have no source column, so schema defaults apply.

Each function takes an optional ``db: AsyncSession`` (see
``app/agents/credentials.py``) — omitted, it opens its own short-lived
session, for callers like the app-startup hook with no request session.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models.ai_model import AIModel

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


def admin_model_to_config(row: AIModel) -> Dict[str, Any]:
    """Convert one AIModel row to the legacy model-config dict."""
    return {
        "model_name": row.model,
        "model_provider": PROVIDER_MAP.get(row.provider, row.provider.lower()),
        "model_endpoint": row.endpoint or None,
        # LLM parameters — legacy schema defaults (no source in AIModel).
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "top_p": DEFAULT_TOP_P,
        "provider_config": {},
        # Pricing: AIModel stores cost per 1K tokens; legacy CostCalculator
        # expects cost per 1M tokens.
        "pricing": {
            "input_tokens_per_million": row.cost_per_1k_in * 1000.0,
            "output_tokens_per_million": row.cost_per_1k_out * 1000.0,
            "currency": "USD",
        },
        "supports_function_calling": True,
        "supports_vision": False,
        "supports_streaming": True,
        "max_context_window": row.context_window,
        "description": row.notes or None,
        "is_active": row.status == "active",
        # Traceability back to the admin row.
        "display_name": row.name,
        "admin_model_id": row.id,
    }


async def get_all_model_configs_dict(db: Optional[AsyncSession] = None) -> Dict[str, Dict[str, Any]]:
    """All *active* model configs keyed by model name (for the startup cache).

    Same contract as the legacy ``model_config_service.get_all_model_configs_dict``.
    """
    stmt = select(AIModel).where(AIModel.status == "active")
    if db is not None:
        rows = (await db.execute(stmt)).scalars().all()
    else:
        async with get_sessionmaker()() as session:
            rows = (await session.execute(stmt)).scalars().all()
    return {row.model: admin_model_to_config(row) for row in rows if row.model}


async def get_model_config(model_name: str, db: Optional[AsyncSession] = None) -> Optional[Dict[str, Any]]:
    """Get a single active model configuration by provider-side model name."""
    stmt = select(AIModel).where(AIModel.model == model_name, AIModel.status == "active")
    if db is not None:
        row = (await db.execute(stmt)).scalar_one_or_none()
    else:
        async with get_sessionmaker()() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
    return admin_model_to_config(row) if row is not None else None


async def count_active_models(db: Optional[AsyncSession] = None) -> int:
    """Number of active models in the ``ai_models`` table."""
    stmt = select(func.count()).select_from(AIModel).where(AIModel.status == "active")
    if db is not None:
        return (await db.execute(stmt)).scalar_one()
    async with get_sessionmaker()() as session:
        return (await session.execute(stmt)).scalar_one()
