"""Temporal durable-workflow layer.

Wraps the same agents exposed inline by `app/api/agent_settings.py` in
Temporal workflows so long-running / durable agent jobs survive restarts,
retry automatically, and report progress over WebSocket.

ALL `temporalio` imports are guarded (see `compat.py`). The FastAPI app
boots and the hermetic test suite runs WITHOUT `temporalio` installed —
the `/api/workflows/*` endpoints simply return 503 until both the
`temporalio` extra is present and a Temporal server is reachable. The
worker (`worker_main.py`) requires the extra and is run as a separate
process.
"""
