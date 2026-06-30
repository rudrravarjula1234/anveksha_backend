"""Temporal workflow definitions.

The legacy backend had three workflows (InterviewContext, ReportGeneration,
AISearch) because each wrapped a different service. In the new backend
every agent runs through one path — `AgentRegistryService.run_agent` — so a
single generic `AgentTaskWorkflow` parametrised by `agent_id` replaces all
three. It runs the agent activity durably with retry, then notifies the
user over WebSocket on completion/failure, and exposes a `status` query.

Only the worker imports + executes this (the worker requires the
`temporalio` extra). The module still imports cleanly without the SDK
thanks to the no-op shims in compat.py, so the rest of the app is fine.
"""

from typing import Any

from app.temporal.compat import RetryPolicy, timedelta, workflow


@workflow.defn
class AgentTaskWorkflow:
    """Durably run one registry agent and notify the requester."""

    def __init__(self) -> None:
        self._status = "initializing"

    @workflow.run
    async def run(
        self,
        agent_id: str,
        context: dict[str, Any],
        user_id: str = "",
    ) -> dict[str, Any]:
        from app.temporal.activities import (
            notify_workflow_completed,
            notify_workflow_failed,
            record_workflow_finished,
            run_agent_activity,
        )

        wf_id = workflow.info().workflow_id
        self._status = "running"
        try:
            result = await workflow.execute_activity(
                run_agent_activity,
                args=[agent_id, context],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            self._status = "completed"
            await workflow.execute_activity(
                record_workflow_finished,
                args=[wf_id, "completed"],
                start_to_close_timeout=timedelta(seconds=10),
            )
            if user_id:
                await workflow.execute_activity(
                    notify_workflow_completed,
                    args=[user_id, wf_id, agent_id, "Agent run complete"],
                    start_to_close_timeout=timedelta(seconds=10),
                )
            return result
        except Exception as exc:  # noqa: BLE001 — report failure, then re-raise for Temporal
            self._status = "failed"
            await workflow.execute_activity(
                record_workflow_finished,
                args=[wf_id, "failed"],
                start_to_close_timeout=timedelta(seconds=10),
            )
            if user_id:
                await workflow.execute_activity(
                    notify_workflow_failed,
                    args=[user_id, wf_id, str(exc)],
                    start_to_close_timeout=timedelta(seconds=10),
                )
            raise

    @workflow.query
    def status(self) -> str:
        return self._status


ALL_WORKFLOWS = [AgentTaskWorkflow]
