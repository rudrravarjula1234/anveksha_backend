"""Durable record of every Temporal workflow run.

A small Mongo-backed ledger (`workflow_runs` collection) so the admin
dashboard can report how many agent workflows were started, are running,
completed, or failed — WITHOUT querying a live Temporal server (which may
be down, and isn't reachable from the hermetic test suite).

Write path:
- `record_started` is called by `workflow_service.start_agent_workflow`
  immediately after Temporal accepts the workflow.
- `record_finished` is called by the durable `record_workflow_finished`
  activity when the workflow reaches a terminal state on the worker.

Read path:
- `get_stats` powers the dashboard's workflow tile.
"""

from datetime import datetime, timezone
from typing import Any

from app.db.mongo import get_database

COLLECTION = "workflow_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def record_started(workflow_id: str, agent_id: str, user_id: str = "") -> None:
    """Insert a `running` ledger row for a freshly started workflow."""
    await get_database()[COLLECTION].insert_one(
        {
            "workflowId": workflow_id,
            "agentId": agent_id,
            "userId": user_id,
            "status": "running",
            "startedAt": _now_iso(),
            "finishedAt": None,
        }
    )


async def record_finished(workflow_id: str, status: str) -> None:
    """Move a row to its terminal state. `status` is 'completed' or 'failed'."""
    await get_database()[COLLECTION].find_one_and_update(
        {"workflowId": workflow_id},
        {"$set": {"status": status, "finishedAt": _now_iso()}},
    )


async def get_stats() -> dict[str, int]:
    """Counts across the whole ledger: total / running / completed / failed."""
    docs: list[dict[str, Any]] = await get_database()[COLLECTION].find().to_list(length=None)
    stats = {"total": len(docs), "running": 0, "completed": 0, "failed": 0}
    for d in docs:
        status = d.get("status")
        if status in ("running", "completed", "failed"):
            stats[status] += 1
    return stats
