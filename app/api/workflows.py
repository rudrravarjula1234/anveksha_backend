"""HTTP + WebSocket API for durable agent workflows.

Mounted at /api/workflows. Every start/status/cancel route delegates to
`workflow_service`, which raises a clean 503 when Temporal isn't available
— so these endpoints are safe to expose even when no worker is running.

The WebSocket endpoint lets the frontend subscribe to completion/failure
events that the workflow's notification activities publish.
"""

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal, get_current_principal, require_roles
from app.db.session import get_session
from app.services import workflow_service
from app.ws.hub import connection_manager

log = logging.getLogger(__name__)

router = APIRouter(tags=["Workflows"])


@router.post("/agent")
async def start_agent_workflow(
    body: dict[str, Any] = Body(...),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start a durable run of a registry agent.

    Body: { agentId: str, context?: object }. The caller's id is used as
    the notification target. Returns { workflowId, status }, or 503 if
    Temporal is unavailable (the inline /api/agents/* endpoints remain the
    synchronous alternative).
    """
    agent_id = body.get("agentId")
    if not agent_id:
        from app.core.exceptions import ValidationError

        raise ValidationError("agentId is required")
    context = body.get("context") or {}
    return await workflow_service.start_agent_workflow(
        agent_id, context, user_id=principal.user_id or "", db=db
    )


@router.get("/{workflow_id}/status")
async def workflow_status(
    workflow_id: str,
    _principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    return await workflow_service.get_workflow_status(workflow_id)


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    _principal: Principal = Depends(require_roles("admin", "interviewer", "company")),
) -> dict[str, Any]:
    return await workflow_service.cancel_workflow(workflow_id)


@router.websocket("/ws/{user_id}")
async def workflow_events(websocket: WebSocket, user_id: str) -> None:
    """Subscribe to this user's workflow events.

    Auth: a `?token=dev_...` query param whose `sub` matches `user_id`
    (mirrors the dev-token scheme). Real JWT validation lands with the
    production auth path.
    """
    token = websocket.query_params.get("token", "")
    from app.auth.dev_tokens import decode_dev_token

    payload = decode_dev_token(token) if token else None
    if not payload or (payload.get("sub") and payload.get("sub") != user_id):
        await websocket.close(code=4001)
        return

    await connection_manager.connect(user_id, websocket)
    try:
        while True:
            # We don't expect client messages; this keeps the socket open.
            await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(user_id, websocket)
