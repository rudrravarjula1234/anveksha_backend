"""Single guarded import site for all Temporal SDK symbols.

Mirrors `app/agents/autogen_compat.py`: when `temporalio` is installed we
re-export the real decorators/classes; when it isn't, we provide no-op
shims so every module that uses `@activity.defn` / `@workflow.defn` still
IMPORTS cleanly (it just can't actually run a worker without the SDK).

`TEMPORAL_AVAILABLE` tells callers which world they're in. The workflow
API and worker check it and degrade gracefully (503 / clear error)
rather than crashing the app.
"""

from __future__ import annotations

try:
    from datetime import timedelta  # noqa: F401  (re-exported for workflow modules)

    from temporalio import activity, workflow
    from temporalio.client import Client
    from temporalio.common import RetryPolicy
    from temporalio.worker import Worker

    TEMPORAL_AVAILABLE = True

except ImportError:  # pragma: no cover - exercised only when extra is absent
    from datetime import timedelta  # noqa: F401

    TEMPORAL_AVAILABLE = False

    Client = None  # type: ignore[assignment]
    Worker = None  # type: ignore[assignment]
    RetryPolicy = None  # type: ignore[assignment]

    class _ActivityShim:
        """No-op stand-in so `@activity.defn` leaves the function callable."""

        @staticmethod
        def defn(fn=None, **_kwargs):
            if fn is None:
                return lambda f: f
            return fn

        def __getattr__(self, _name):  # activity.info(), etc. — never called w/o SDK
            raise RuntimeError("temporalio is not installed")

    class _WorkflowShim:
        """No-op stand-in so `@workflow.defn` / `@workflow.run` import cleanly."""

        @staticmethod
        def defn(cls=None, **_kwargs):
            if cls is None:
                return lambda c: c
            return cls

        @staticmethod
        def run(fn):
            return fn

        @staticmethod
        def query(fn):
            return fn

        def __getattr__(self, _name):
            raise RuntimeError("temporalio is not installed")

    activity = _ActivityShim()  # type: ignore[assignment]
    workflow = _WorkflowShim()  # type: ignore[assignment]
