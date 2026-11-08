"""HTTP layer for `/api/agents` — the agentic framework surface.

Routes:

    GET    /api/agents/status                  — framework availability + config summary
    GET    /api/agents/credentials             — masked provider credentials (admin)
    POST   /api/agents/credentials             — upsert a provider credential (admin)
    DELETE /api/agents/credentials/{provider}  — remove a provider credential (admin)
    GET    /api/agents/token-usage             — recent token usage rows (admin)
    POST   /api/agents/feedback                — generate interview feedback (admin/interviewer)

Mounted in `app.main` at prefix="/api/agents" (alongside
`agent_settings.shared_router`'s different sub-paths on the same prefix).

The agents package is import-safe without the optional AutoGen packages;
`POST /feedback` returns 503 until they are installed and a provider
credential is configured (see ``app/agents/README.md``).
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import credentials as credential_store
from app.agents import model_config_adapter
from app.agents.autogen_compat import AUTOGEN_AVAILABLE
from app.agents.feedback_agents import DEFAULT_FEEDBACK_MODEL
from app.agents.feedback_service import generate_feedback_direct
from app.agents.schemas import (
    CredentialMasked,
    CredentialUpsert,
    FeedbackRequest,
    TokenUsage,
)
from app.agents.token_usage import store as token_usage_store
from app.auth.deps import get_current_principal, require_roles
from app.core.exceptions import AppError, NotFoundError
from app.db.session import get_session

router = APIRouter(tags=["Agents"])

# Providers that work without an API key (local / keyless deployments).
_KEYLESS_PROVIDERS = {"ollama"}


# ── Status ──────────────────────────────────────────────────────────────


@router.get("/status", dependencies=[Depends(get_current_principal)])
async def agent_status(db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Report framework availability and configuration state."""
    providers = await credential_store.configured_providers(db=db)
    active_models = await model_config_adapter.count_active_models(db=db)
    return {
        "autogen_available": AUTOGEN_AVAILABLE,
        "configured_providers": providers,
        "active_model_count": active_models,
        "default_feedback_model": DEFAULT_FEEDBACK_MODEL,
        "ready": AUTOGEN_AVAILABLE and active_models > 0 and len(providers) > 0,
    }


# ── Credentials (admin) ─────────────────────────────────────────────────


@router.get(
    "/credentials",
    response_model=list[CredentialMasked],
    dependencies=[Depends(require_roles("admin"))],
)
async def list_credentials(db: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """Masked list — plaintext keys never leave the server."""
    return await credential_store.list_credentials(active_only=False, db=db)


@router.post(
    "/credentials",
    response_model=CredentialMasked,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def upsert_credential(
    payload: CredentialUpsert, db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Create or replace the credential for a provider (key encrypted at rest)."""
    return await credential_store.upsert_credential(
        provider=payload.provider,
        api_key=payload.api_key,
        endpoint=payload.endpoint,
        extra=payload.additional_config,
        db=db,
    )


@router.delete(
    "/credentials/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("admin"))],
)
async def delete_credential(provider: str, db: AsyncSession = Depends(get_session)) -> None:
    removed = await credential_store.delete_credential(provider, db=db)
    if not removed:
        raise NotFoundError(f"No active credential for provider '{provider}'")


# ── Token usage (admin) ─────────────────────────────────────────────────


@router.get(
    "/token-usage",
    response_model=list[TokenUsage],
    dependencies=[Depends(require_roles("admin"))],
)
async def recent_token_usage(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
) -> list[TokenUsage]:
    """Most recent token usage rows, newest first."""
    return await token_usage_store.list_recent(limit=limit, db=db)


# ── Interview feedback (admin or interviewer) ───────────────────────────


@router.post(
    "/feedback",
    dependencies=[Depends(require_roles("admin", "interviewer"))],
)
async def generate_feedback(
    payload: FeedbackRequest,
    model: Optional[str] = Query(
        default=None,
        description="Override the model used (must be active in ai_models).",
    ),
) -> dict[str, Any]:
    """Generate structured interview feedback from a transcript.

    Returns 503 when the AutoGen extras are not installed or no usable
    provider credential is configured.

    Deliberately does NOT take `Depends(get_session)` — the LLM call below
    can run for seconds, and holding a connection checked out of the
    (small, fixed-size) pool for that long wastes a slot other requests
    need. The config/credential lookups each open their own short-lived
    session instead (see `app/agents/credentials.py`).
    """
    if not AUTOGEN_AVAILABLE:
        raise AppError(
            "Agent framework dependencies not installed. Install the optional "
            "agent extras (autogen-agentchat / autogen-ext, see "
            "app/agents/README.md) to enable feedback generation.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Resolve the model that will actually run, then verify its provider has
    # a credential — fail fast with a clear 503 instead of a provider error.
    preferred = model or DEFAULT_FEEDBACK_MODEL
    model_config = await model_config_adapter.get_model_config(preferred)
    if model_config is None:
        configs = await model_config_adapter.get_all_model_configs_dict()
        if not configs:
            raise AppError(
                "No active models registered in ai_models. Create one via "
                "POST /api/admin/models first.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        model_config = next(iter(configs.values()))

    provider = model_config["model_provider"]
    if provider not in _KEYLESS_PROVIDERS:
        credential = await credential_store.get_credential(provider)
        if credential is None:
            raise AppError(
                f"No API credential configured for provider '{provider}'. "
                "Add one via POST /api/agents/credentials.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    metadata = payload.metadata.model_dump(exclude_none=True) if payload.metadata else None
    result = await generate_feedback_direct(
        transcript=payload.transcript,
        metadata=metadata,
        model_name=model_config["model_name"],
    )
    return result
