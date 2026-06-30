"""Temporal worker entrypoint.

Run as a SEPARATE process (docker service `temporal-worker`):

    python -m app.temporal.worker_main

Requires the `temporalio` extra. Connects Mongo (so activities can read
seed/agent data), then runs a Worker on the configured task queue with
the AgentTaskWorkflow + all activities registered.
"""

import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.temporal.compat import TEMPORAL_AVAILABLE

log = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    if not TEMPORAL_AVAILABLE:
        raise SystemExit(
            "Cannot start worker: the 'temporalio' extra is not installed. "
            "Install with: pip install '.[agents,temporal]'"
        )

    from app.db.mongo import connect_to_mongo
    from app.temporal.activities import ALL_ACTIVITIES
    from app.temporal.client import get_temporal_client
    from app.temporal.compat import Worker
    from app.temporal.workflows import ALL_WORKFLOWS

    await connect_to_mongo()
    log.info("Worker: Mongo connected")

    client = await get_temporal_client()
    worker = Worker(  # type: ignore[operator]
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=ALL_WORKFLOWS,
        activities=ALL_ACTIVITIES,
    )
    log.info(
        "Worker starting — queue=%s workflows=%d activities=%d",
        settings.TEMPORAL_TASK_QUEUE,
        len(ALL_WORKFLOWS),
        len(ALL_ACTIVITIES),
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
