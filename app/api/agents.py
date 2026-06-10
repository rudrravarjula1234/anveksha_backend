"""HTTP layer for `/api/agents` — the agentic framework surface.

Routes:

    GET    /api/agents/status                  — framework availability + config summary
    GET    /api/agents/credentials             — masked provider credentials (admin)
    POST   /api/agents/credentials             — upsert a provider credential (admin)
    DELETE /api/agents/credentials/{provider}  — remove a provider credential (admin)
    GET    /api/agents/token-usage             — recent token usage rows (admin)
    POST   /api/agents/feedback                — generate interview feedback (admin/interviewer)

NOT mounted in `app.main` yet — the integrator wires the prefix.

The agents package is import-safe without the optional AutoGen packages;
`POST /feedback` returns 503 until they are installed and a provider
credential is configured (see ``app/agents/README.md``).
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

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

router = APIRouter(tags=["Agents"])

# Providers that work without an API key (local / keyless deployments).
_KEYLESS_PROVIDERS = {"ollama"}


# ── Status ──────────────────────────────────────────────────────────────


@router.get("/status", dependencies=[Depends(get_current_principal)])
async def agent_status() -> dict[str, Any]:
    """Report framework availability and configuration state."""
    providers = await credential_store.configured_providers()
    active_models = await model_config_adapter.count_active_models()
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
async def list_credentials() -> list[dict[str, Any]]:
    """Masked list — plaintext keys never leave the server."""
    return await credential_store.list_credentials(active_only=False)


@router.post(
    "/credentials",
    response_model=CredentialMasked,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def upsert_credential(payload: CredentialUpsert) -> dict[str, Any]:
    """Create or replace the credential for a provider (key encrypted at rest)."""
    return await credential_store.upsert_credential(
        provider=payload.provider,
        api_key=payload.api_key,
        endpoint=payload.endpoint,
        extra=payload.additional_config,
    )


@router.delete(
    "/credentials/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("admin"))],
)
async def delete_credential(provider: str) -> None:
    removed = await credential_store.delete_credential(provider)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active credential for provider '{provider}'",
        )


# ── Token usage (admin) ─────────────────────────────────────────────────


@router.get(
    "/token-usage",
    response_model=list[TokenUsage],
    dependencies=[Depends(require_roles("admin"))],
)
async def recent_token_usage(
    limit: int = Query(default=50, ge=1, le=500),
) -> list[TokenUsage]:
    """Most recent token usage rows, newest first."""
    return await token_usage_store.list_recent(limit=limit)


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
    """
    if not AUTOGEN_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Agent framework dependencies not installed. Install the optional "
                "agent extras (autogen-agentchat / autogen-ext, see "
                "app/agents/README.md) to enable feedback generation."
            ),
        )

    # Resolve the model that will actually run, then verify its provider has
    # a credential — fail fast with a clear 503 instead of a provider error.
    preferred = model or DEFAULT_FEEDBACK_MODEL
    model_config = await model_config_adapter.get_model_config(preferred)
    if model_config is None:
        configs = await model_config_adapter.get_all_model_configs_dict()
        if not configs:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "No active models registered in ai_models. Create one via "
                    "POST /api/admin/models first."
                ),
            )
        model_config = next(iter(configs.values()))

    provider = model_config["model_provider"]
    if provider not in _KEYLESS_PROVIDERS:
        credential = await credential_store.get_credential(provider)
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"No API credential configured for provider '{provider}'. "
                    "Add one via POST /api/agents/credentials."
                ),
            )

    metadata = payload.metadata.model_dump(exclude_none=True) if payload.metadata else None
    result = await generate_feedback_direct(
        transcript=payload.transcript,
        metadata=metadata,
        model_name=model_config["model_name"],
    )
    return result
