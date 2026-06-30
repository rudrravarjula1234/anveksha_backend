"""Platform metrics dashboard — ledger, aggregation service, and API.

Hermetic: uses the FakeCollection stub. Temporal stats come from the
Mongo-backed `workflow_runs` ledger (not a live Temporal server), so they
are fully testable without the SDK.
"""

import base64
import json

import pytest
from httpx import AsyncClient

from app.services import workflow_runs_service as wruns


# ── workflow_runs ledger ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_started_shows_as_running(fake_db):  # noqa: ARG001
    await wruns.record_started("agent-gray-1", "gray_analyzer", "usr_cand_001")
    stats = await wruns.get_stats()
    assert stats == {"total": 1, "running": 1, "completed": 0, "failed": 0}


@pytest.mark.asyncio
async def test_record_finished_moves_running_to_completed(fake_db):  # noqa: ARG001
    await wruns.record_started("agent-gray-1", "gray_analyzer", "u1")
    await wruns.record_finished("agent-gray-1", "completed")
    stats = await wruns.get_stats()
    assert stats == {"total": 1, "running": 0, "completed": 1, "failed": 0}


@pytest.mark.asyncio
async def test_record_finished_failure_counts_as_failed(fake_db):  # noqa: ARG001
    await wruns.record_started("agent-x-2", "report_generator", "u1")
    await wruns.record_finished("agent-x-2", "failed")
    stats = await wruns.get_stats()
    assert stats == {"total": 1, "running": 0, "completed": 0, "failed": 1}


# ── durable finish activity (worker path, callable directly) ───────────────


@pytest.mark.asyncio
async def test_record_workflow_finished_activity_updates_ledger(fake_db):  # noqa: ARG001
    from app.temporal.activities import record_workflow_finished

    await wruns.record_started("agent-rep-9", "report_generator", "u1")
    ok = await record_workflow_finished("agent-rep-9", "completed")
    assert ok is True
    stats = await wruns.get_stats()
    assert stats["completed"] == 1 and stats["running"] == 0


# ── aggregation service ────────────────────────────────────────────────────


async def _seed_metrics_fixture(db) -> None:
    from app.db.seed import seed_users
    from app.db.seed_agent_registry import seed_agent_registry

    await seed_agent_registry()  # 6 agents, all enabled
    await seed_users()  # 8 users (4 candidate / 2 interviewer / 2 company / 2 admin)
    await db["bots"].insert_one({"id": "bot1", "status": "active"})
    await db["bots"].insert_one({"id": "bot2", "status": "draft"})
    await db["ai_models"].insert_one({"id": "m1", "status": "active"})
    await db["ai_models"].insert_one({"id": "m2", "status": "inactive"})
    await db["token_usage"].insert_one(
        {"model_name": "gpt-4o", "input_tokens": 60, "output_tokens": 40,
         "total_tokens": 100, "total_cost": 0.01}
    )
    await db["token_usage"].insert_one(
        {"model_name": "claude", "input_tokens": 120, "output_tokens": 80,
         "total_tokens": 200, "total_cost": 0.02}
    )
    await wruns.record_started("wf-1", "gray_analyzer", "u1")
    await wruns.record_started("wf-2", "report_generator", "u1")
    await wruns.record_finished("wf-2", "completed")


@pytest.mark.asyncio
async def test_platform_metrics_aggregates_all_sources(fake_db):
    from app.services.platform_metrics_service import PlatformMetricsService

    await _seed_metrics_fixture(fake_db)
    m = await PlatformMetricsService().metrics()

    assert m.agents.total == 6 and m.agents.enabled == 6 and m.agents.disabled == 0
    assert m.bots.total == 2 and m.bots.active == 1 and m.bots.draft == 1
    assert m.models.total == 2 and m.models.active == 1 and m.models.inactive == 1
    assert m.users.total == 8
    assert m.users.candidates == 4 and m.users.interviewers == 2
    assert m.users.companies == 2 and m.users.admins == 2
    assert m.tokens.totalTokens == 300 and m.tokens.totalRequests == 2
    assert m.tokens.totalCostUsd == pytest.approx(0.03)
    assert {b.modelName for b in m.tokens.byModel} == {"gpt-4o", "claude"}
    assert m.workflows.total == 2 and m.workflows.running == 1 and m.workflows.completed == 1
    # Temporal SDK absent in the hermetic suite.
    assert m.workflows.available is False


# ── API endpoint (+ seeds make it non-empty) ───────────────────────────────


def _token(role: str, sub: str) -> str:
    payload = json.dumps({"sub": sub, "role": role})
    return "dev_" + base64.b64encode(payload.encode()).decode()


@pytest.mark.asyncio
async def test_platform_metrics_endpoint_returns_full_envelope(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.get("/api/admin/metrics/platform", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("agents", "bots", "models", "users", "tokens", "workflows", "generatedAt"):
        assert key in body
    # Seeded data makes the dashboard meaningful out of the box.
    assert body["agents"]["total"] == 6
    assert body["tokens"]["totalTokens"] > 0
    assert len(body["tokens"]["byModel"]) > 0
    assert body["workflows"]["total"] > 0
    assert body["workflows"]["failed"] >= 1  # the seed includes a failed run


@pytest.mark.asyncio
async def test_platform_metrics_endpoint_forbidden_for_non_admin(client: AsyncClient):
    r = await client.get(
        "/api/admin/metrics/platform",
        headers={"Authorization": f"Bearer {_token('candidate', 'usr_cand_001')}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_platform_metrics_endpoint_requires_auth(client: AsyncClient):
    r = await client.get("/api/admin/metrics/platform")
    assert r.status_code == 401
