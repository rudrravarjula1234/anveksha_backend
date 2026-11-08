"""Service layer for starting/inspecting Temporal workflows.

Every function goes through `get_temporal_client()`, which raises a clean
503 (`TemporalUnavailableError`) when the SDK is missing or the server is
unreachable — so the API degrades gracefully instead of 500-ing.

Workflow ids are deterministic-ish: `agent-{agent_id}-{short}` where short
is derived from the caller-supplied context (no Date/random in workflow
code, but the *service* may use uuid since it runs outside the sandbox).
"""

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.temporal.client import get_temporal_client

log = logging.getLogger(__name__)


async def start_agent_workflow(
    agent_id: str, context: dict[str, Any], user_id: str = "", db: Optional[AsyncSession] = None
) -> dict[str, Any]:
    """Kick off a durable AgentTaskWorkflow. Returns the workflow id."""
    client = await get_temporal_client()
    # Lazy import — the workflow module references the SDK and is only
    # needed once we know Temporal is available.
    from app.temporal.workflows import AgentTaskWorkflow

    settings = get_settings()
    wf_id = f"agent-{agent_id}-{uuid.uuid4().hex[:8]}"
    handle = await client.start_workflow(
        AgentTaskWorkflow.run,
        args=[agent_id, context, user_id],
        id=wf_id,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )
    # Ledger the run so the admin dashboard can count it even though
    # Temporal's own visibility store isn't queried by the API.
    from app.services.workflow_runs_service import record_started

    await record_started(handle.id, agent_id, user_id, db=db)
    log.info("Started workflow %s (agent=%s)", handle.id, agent_id)
    return {"workflowId": handle.id, "status": "started"}


async def get_workflow_status(workflow_id: str) -> dict[str, Any]:
    client = await get_temporal_client()
    from app.temporal.workflows import AgentTaskWorkflow

    handle = client.get_workflow_handle(workflow_id)
    desc = await handle.describe()
    status_name = desc.status.name if desc.status else "UNKNOWN"
    out: dict[str, Any] = {"workflowId": workflow_id, "status": status_name}
    # Best-effort custom status query (only meaningful while RUNNING).
    try:
        out["customStatus"] = await handle.query(AgentTaskWorkflow.status)
    except Exception:  # noqa: BLE001 — query unavailable once closed
        pass
    return out


async def cancel_workflow(workflow_id: str) -> dict[str, Any]:
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    await handle.cancel()
    return {"workflowId": workflow_id, "cancelled": True}
