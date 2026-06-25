"""Temporal activities.

These wrap the SAME agent execution the inline endpoints use
(`AgentRegistryService.run_agent`) plus WebSocket notifications. Because
`@activity.defn` is a no-op shim when `temporalio` is absent
(see compat.py), every function here stays a plain async callable and is
unit-testable directly — no Temporal server needed.

Inside a real worker these run durably with the workflow's retry policy.
"""

import logging
from typing import Any

from app.temporal.compat import activity
from app.ws.hub import connection_manager

log = logging.getLogger(__name__)


@activity.defn
async def run_agent_activity(agent_id: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run a registry agent durably. Returns the AgentRunResult as a dict.

    Imports the service lazily so this module imports cleanly in the
    Temporal workflow sandbox (which restricts top-level imports).
    """
    from app.services.agent_registry_service import AgentRegistryService

    service = AgentRegistryService()
    result = await service.run_agent(agent_id, context)
    return result.model_dump()


@activity.defn
async def notify_workflow_completed(
    user_id: str, workflow_id: str, workflow_type: str, summary: str
) -> bool:
    if not user_id:
        return False
    await connection_manager.send_to_user(
        user_id,
        {
            "type": "workflow_completed",
            "workflowId": workflow_id,
            "workflowType": workflow_type,
            "summary": summary,
        },
    )
    return True


@activity.defn
async def notify_workflow_failed(user_id: str, workflow_id: str, error: str) -> bool:
    if not user_id:
        return False
    await connection_manager.send_to_user(
        user_id,
        {
            "type": "workflow_failed",
            "workflowId": workflow_id,
            "error": error,
        },
    )
    return True


# Registered on the worker (see worker_main.py). Kept as a module list so
# the worker and tests share one source of truth.
ALL_ACTIVITIES = [
    run_agent_activity,
    notify_workflow_completed,
    notify_workflow_failed,
]
