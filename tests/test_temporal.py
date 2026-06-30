"""Temporal layer — the pieces testable WITHOUT a Temporal server.

The hermetic suite does NOT install `temporalio`, so these exercise the
graceful-degradation path (503) and the plain-async activity / ws-hub
logic. Actual durable execution is covered by running the worker against a
real Temporal server (docker compose) — out of scope for pytest.
"""

import json

import pytest
from httpx import AsyncClient

from app.temporal.activities import (
    notify_workflow_completed,
    notify_workflow_failed,
    run_agent_activity,
)
from app.temporal.compat import TEMPORAL_AVAILABLE
from app.ws.hub import ConnectionManager


# ── WebSocket hub (pure, no Temporal) ──────────────────────────────────────


class _FakeSocket:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("socket dead")
        self.sent.append(text)


@pytest.mark.asyncio
async def test_ws_hub_delivers_to_all_user_sockets():
    mgr = ConnectionManager()
    a, b = _FakeSocket(), _FakeSocket()
    await mgr.connect("u1", a)
    await mgr.connect("u1", b)
    delivered = await mgr.send_to_user("u1", {"type": "ping"})
    assert delivered == 2
    assert json.loads(a.sent[0]) == {"type": "ping"}


@pytest.mark.asyncio
async def test_ws_hub_prunes_dead_sockets():
    mgr = ConnectionManager()
    live, dead = _FakeSocket(), _FakeSocket(fail=True)
    await mgr.connect("u1", live)
    await mgr.connect("u1", dead)
    delivered = await mgr.send_to_user("u1", {"type": "x"})
    assert delivered == 1
    assert mgr.connection_count("u1") == 1  # dead one pruned


@pytest.mark.asyncio
async def test_ws_hub_send_to_unknown_user_is_noop():
    mgr = ConnectionManager()
    assert await mgr.send_to_user("nobody", {"type": "x"}) == 0


# ── Activities (pure async — @activity.defn is a no-op shim here) ───────────


@pytest.mark.asyncio
async def test_run_agent_activity_returns_envelope(fake_db):  # noqa: ARG001 — seeds DB
    from app.db.seed_agent_registry import seed_agent_registry

    # Importing registers the deterministic fallbacks (a side effect that
    # main.create_app() performs at startup — done explicitly here since the
    # ASGI lifespan doesn't run for this unit-level test).
    import app.services.agent_fallbacks  # noqa: F401, PLC0415

    await seed_agent_registry()
    out = await run_agent_activity("gray_analyzer", {"candidateId": "usr_cand_001"})
    assert out["agentId"] == "gray_analyzer"
    # No LLM creds in tests → deterministic fallback path.
    assert out["source"] == "fallback"
    assert isinstance(out["output"], str) and out["output"]


@pytest.mark.asyncio
async def test_notify_activities_noop_without_user():
    assert await notify_workflow_completed("", "wf1", "agent", "done") is False
    assert await notify_workflow_failed("", "wf1", "boom") is False


# ── Workflow API graceful degradation (temporalio absent in tests) ─────────


@pytest.mark.asyncio
async def test_temporalio_absent_in_test_env():
    # Guard assumption: the hermetic suite runs WITHOUT the extra, so the
    # API must degrade to 503 rather than 500. If this ever flips, the
    # degradation tests below stop proving anything.
    assert TEMPORAL_AVAILABLE is False


@pytest.mark.asyncio
async def test_start_agent_workflow_503_without_temporal(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.post(
        "/api/workflows/agent",
        json={"agentId": "gray_analyzer", "context": {}},
        headers=admin_headers,
    )
    assert r.status_code == 503
    assert r.json()["code"] == "temporal_unavailable"


@pytest.mark.asyncio
async def test_start_agent_workflow_requires_agent_id(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.post("/api/workflows/agent", json={}, headers=admin_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_workflow_status_503_without_temporal(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.get("/api/workflows/agent-x-123/status", headers=admin_headers)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_workflow_endpoints_require_auth(client: AsyncClient):
    r = await client.post("/api/workflows/agent", json={"agentId": "x"})
    assert r.status_code == 401
