"""Platform metrics dashboard — ledger, aggregation service, and API.

`workflow_runs` and `token_usage` are Postgres-backed (see the migration
plan's Stage 10) — Temporal stats come from the `workflow_runs` ledger
(not a live Temporal server), so they are fully testable without the SDK.
"""

import base64
import json
import uuid

import pytest
from httpx import AsyncClient

from app.services import workflow_runs_service as wruns

# ── workflow_runs ledger ───────────────────────────────────────────────────
#
# `pg_session` isolates each test via a rolled-back SAVEPOINT (see
# conftest.py), so passing it explicitly keeps these exact-count
# assertions valid without touching the real, cross-test-persistent
# engine that `get_sessionmaker()`'s self-contained-session fallback
# would use.


@pytest.mark.asyncio
async def test_record_started_shows_as_running(pg_session):
    await wruns.record_started("agent-gray-1", "gray_analyzer", "usr_cand_001", db=pg_session)
    stats = await wruns.get_stats(db=pg_session)
    assert stats == {"total": 1, "running": 1, "completed": 0, "failed": 0}


@pytest.mark.asyncio
async def test_record_finished_moves_running_to_completed(pg_session):
    await wruns.record_started("agent-gray-1", "gray_analyzer", "u1", db=pg_session)
    await wruns.record_finished("agent-gray-1", "completed", db=pg_session)
    stats = await wruns.get_stats(db=pg_session)
    assert stats == {"total": 1, "running": 0, "completed": 1, "failed": 0}


@pytest.mark.asyncio
async def test_record_finished_failure_counts_as_failed(pg_session):
    await wruns.record_started("agent-x-2", "report_generator", "u1", db=pg_session)
    await wruns.record_finished("agent-x-2", "failed", db=pg_session)
    stats = await wruns.get_stats(db=pg_session)
    assert stats == {"total": 1, "running": 0, "completed": 0, "failed": 1}


# ── durable finish activity (worker path, callable directly) ───────────────


@pytest.mark.asyncio
async def test_record_workflow_finished_activity_updates_ledger(monkeypatch: pytest.MonkeyPatch):
    """`record_workflow_finished` is a Temporal activity — no FastAPI
    request cycle, so (like `run_agent_activity` in test_temporal.py) it
    opens its own session against the real engine rather than using
    `pg_session`'s rolled-back-transaction isolation. Uses a fresh random
    workflow id per run (not one of the fixed seed ids) since these rows
    are genuinely new inserts, not idempotent seed data, and the
    real-commit-based check reads back the one row directly rather than
    a global count that would grow across repeated runs. Cleans its own
    row up afterward — a real, uncommitted-nowhere-else row like this
    would otherwise leak into any other test's exact-count assertions
    against the same shared test database within this run."""
    from app.core.config import get_settings
    from app.db.session import connect_to_db, get_sessionmaker
    from app.models.workflow import WorkflowRun
    from app.temporal.activities import record_workflow_finished

    monkeypatch.setattr(get_settings(), "DATABASE_URL", get_settings().TEST_DATABASE_URL)
    await connect_to_db()

    wf_id = f"agent-rep-{uuid.uuid4().hex[:8]}"
    await wruns.record_started(wf_id, "report_generator", "u1")
    ok = await record_workflow_finished(wf_id, "completed")
    assert ok is True

    async with get_sessionmaker()() as db:
        row = await db.get(WorkflowRun, wf_id)
        assert row is not None
        assert row.status == "completed"
        assert row.finished_at is not None
        await db.delete(row)
        await db.commit()


# ── aggregation service ────────────────────────────────────────────────────


async def _seed_metrics_fixture(pg_session) -> None:
    from app.db.seed import seed_users
    from app.db.seed_agent_registry import seed_agent_registry
    from app.models.ai_model import AIModel
    from app.models.bot import Bot
    from app.models.token_usage import TokenUsage

    await seed_agent_registry(pg_session)  # 6 agents, all enabled
    await seed_users(pg_session)  # 8 users (4 candidate / 2 interviewer / 2 company / 2 admin)
    pg_session.add_all(
        [
            AIModel(id="m1", name="m1", provider="OpenAI", model="m1", status="active"),
            AIModel(id="m2", name="m2", provider="OpenAI", model="m2", status="inactive"),
            Bot(id="bot1", name="bot1", status="active"),
            Bot(id="bot2", name="bot2", status="draft"),
            TokenUsage(
                id="tok_test1", request_id="req_test1", model_name="gpt-4o", orchestration_type="direct",
                input_tokens=60, output_tokens=40, total_tokens=100, total_cost=0.01,
            ),
            TokenUsage(
                id="tok_test2", request_id="req_test2", model_name="claude", orchestration_type="direct",
                input_tokens=120, output_tokens=80, total_tokens=200, total_cost=0.02,
            ),
        ]
    )
    await pg_session.flush()
    await wruns.record_started("wf-1", "gray_analyzer", "u1", db=pg_session)
    await wruns.record_started("wf-2", "report_generator", "u1", db=pg_session)
    await wruns.record_finished("wf-2", "completed", db=pg_session)


@pytest.mark.asyncio
async def test_platform_metrics_aggregates_all_sources(pg_session):
    from app.services.platform_metrics_service import PlatformMetricsService

    await _seed_metrics_fixture(pg_session)
    m = await PlatformMetricsService(pg_session).metrics()

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
