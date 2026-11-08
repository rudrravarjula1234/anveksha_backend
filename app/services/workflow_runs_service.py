"""Ledger of every Temporal workflow run (`workflow_runs` table), so the
admin dashboard can report started/running/completed/failed counts
without querying a live Temporal server.

Each function takes an optional `db: AsyncSession` — pass the
request-scoped session when available, otherwise a short-lived session is
opened and committed internally (e.g. from the Temporal activity that
records a finished run).
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import utc_now
from app.db.session import session_scope
from app.models.workflow import WorkflowRun, WorkflowRunStatusCount

_STATUSES = ("running", "completed", "failed")


async def record_started(
    workflow_id: str, agent_id: str, user_id: Optional[str] = None, db: Optional[AsyncSession] = None
) -> None:
    """Insert a `running` ledger row for a freshly started workflow."""
    row = WorkflowRun(workflow_id=workflow_id, agent_id=agent_id, user_id=user_id or None, status="running")
    async with session_scope(db, write=True) as session:
        session.add(row)


async def _apply_finished(session: AsyncSession, workflow_id: str, status: str) -> None:
    row = await session.get(WorkflowRun, workflow_id)
    if row is not None:
        row.status = status
        row.finished_at = utc_now()


async def record_finished(workflow_id: str, status: str, db: Optional[AsyncSession] = None) -> None:
    """Move a row to its terminal state. `status` is 'completed' or 'failed'."""
    async with session_scope(db, write=True) as session:
        await _apply_finished(session, workflow_id, status)


async def _query_stats(session: AsyncSession) -> dict[str, int]:
    # Trigger-maintained rollup: three rows, not a scan of every run.
    stmt = select(WorkflowRunStatusCount.status, WorkflowRunStatusCount.runs)
    counts = {status: int(n) for status, n in (await session.execute(stmt)).all()}
    return {
        "total": sum(counts.values()),
        "running": counts.get("running", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
    }


async def get_stats(db: Optional[AsyncSession] = None) -> dict[str, int]:
    """Counts across the whole ledger: total / running / completed / failed."""
    async with session_scope(db) as session:
        return await _query_stats(session)
