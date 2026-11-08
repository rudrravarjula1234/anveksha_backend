"""Ledger of every Temporal workflow run — storage layer. `workflow_id`
(the real Temporal workflow id, globally unique per execution) is the
primary key; no redundant surrogate id.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_WORKFLOW_STATUSES = ("running", "completed", "failed")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        # Matches the migration plan's standards checklist: composite
        # index for the actual access pattern (dashboard counts/filters
        # by status, ordered by recency).
        Index("ix_workflow_runs_status_started_at", "status", "started_at"),
    )

    workflow_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Not indexed: written once per run, never filtered on.
    agent_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # NULL = no caller id. Soft ref (no FK): dev-token callers carry a `sub`
    # that need not exist in `users`, and a run must still be ledgered.
    user_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(*_WORKFLOW_STATUSES, name="workflow_run_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="running",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowRunStatusCount(Base):
    """Run count per status, maintained by the statement-level
    `trg_workflow_run_counts_{ins,upd,del,trunc}` triggers (migration
    0001) — never written by the app. The admin dashboard reads
    these three rows instead of grouping the whole run ledger."""

    __tablename__ = "workflow_run_status_counts"

    status: Mapped[str] = mapped_column(String(20), primary_key=True)
    runs: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
