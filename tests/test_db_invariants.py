"""Database invariants the API relies on: RLS on every table, the
trigger-maintained rollups, the approval constraints, the single-query
caller lookup, and the timestamp wire format."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, event, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.timefmt import utc_now
from app.models.approvals import InterviewerApproval
from app.models.token_usage import TokenUsage, TokenUsageModelTotals
from app.models.workflow import WorkflowRunStatusCount
from app.services import workflow_runs_service as wruns
from tests.helpers import hdr

AARAV = ("usr_cand_001", "candidate")
ADMIN = ("usr_adm_001", "admin")


async def test_every_public_table_has_rls(pg_session: AsyncSession):
    """Supabase exposes `public` to the anon key through the Data API, so a
    table without RLS is world-readable. New tables must call
    app.db.rls.enable_rls_sql in their migration."""
    rows = await pg_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND NOT rowsecurity")
    )
    assert rows.scalars().all() == []


async def test_auth_me_loads_the_caller_once(client: AsyncClient, pg_engine: AsyncEngine):
    statements: list[str] = []

    def _record(conn, cursor, statement, *_):
        statements.append(statement)

    event.listen(pg_engine.sync_engine, "before_cursor_execute", _record)
    try:
        r = await client.get("/api/auth/me", headers=hdr(*AARAV))
    finally:
        event.remove(pg_engine.sync_engine, "before_cursor_execute", _record)
    assert r.status_code == 200
    user_reads = [s for s in statements if "FROM users" in s]
    role_reads = [s for s in statements if s.lstrip().startswith("SELECT user_roles")]
    # One joined users+roles query; AuthService.me answers from the identity map.
    assert len(user_reads) == 1, statements
    assert role_reads == [], statements


# ── Rollups ──────────────────────────────────────────────────────────────


async def test_token_totals_follow_inserts_updates_and_deletes(client: AsyncClient, pg_session: AsyncSession):
    async def totals(model: str):
        return await pg_session.get(TokenUsageModelTotals, model, populate_existing=True)

    rows = [
        dict(id=f"tu_bulk_{i}", request_id=f"rq_bulk_{i}", model_name="bulk-a" if i % 2 else "bulk-b",
             orchestration_type="direct", input_tokens=10, output_tokens=5, total_tokens=15,
             input_cost=0.001, output_cost=0.002, total_cost=0.003)
        for i in range(200)
    ]
    await pg_session.execute(insert(TokenUsage), rows)  # multi-row statement
    a, b = await totals("bulk-a"), await totals("bulk-b")
    assert (a.requests, a.total_tokens, round(a.total_cost, 6)) == (100, 1500, 0.3)
    assert (b.requests, b.total_tokens) == (100, 1500)

    # Moving rows between models moves their totals; an emptied model disappears.
    await pg_session.execute(
        update(TokenUsage).where(TokenUsage.model_name == "bulk-b").values(model_name="bulk-a")
    )
    assert (await totals("bulk-a")).requests == 200
    assert await totals("bulk-b") is None

    await pg_session.execute(delete(TokenUsage).where(TokenUsage.id == "tu_bulk_0"))
    a = await totals("bulk-a")
    assert (a.requests, a.input_tokens, a.output_tokens) == (199, 1990, 995)

    # Platform metrics read the same numbers.
    r = await client.get("/api/admin/metrics/platform", headers=hdr(*ADMIN))
    assert r.status_code == 200
    by_model = {m["modelName"]: m for m in r.json()["tokens"]["byModel"]}
    assert by_model["bulk-a"]["requests"] == 199


@pytest.mark.usefixtures("client")  # seeds the database
async def test_truncate_empties_the_rollups(pg_session: AsyncSession):
    await wruns.record_started("wf-trunc-1", "gray_analyzer", None, db=pg_session)
    await pg_session.execute(
        insert(TokenUsage),
        [dict(id="tu_trunc", request_id="rq_trunc", model_name="trunc-m", orchestration_type="direct",
              input_tokens=1, output_tokens=1, total_tokens=2, input_cost=0, output_cost=0, total_cost=0)],
    )
    await pg_session.execute(text("TRUNCATE token_usage, workflow_runs CASCADE"))
    assert (await pg_session.execute(select(TokenUsageModelTotals))).first() is None
    assert (await pg_session.execute(select(WorkflowRunStatusCount))).first() is None


# ── Interviewer approvals ────────────────────────────────────────────────


def _approval(id: str, **kw) -> InterviewerApproval:
    fields = dict(
        candidate_id="usr_cand_001", candidate_name="Aarav Rao", candidate_initials="AR", dossier_id="ANV-0001",
        requested_skill=".NET Microservices", origin="self-requested", submitted_at=utc_now(), status="pending",
    )
    return InterviewerApproval(id=id, **(fields | kw))


async def test_one_pending_approval_per_candidate_skill(client: AsyncClient, pg_session: AsyncSession):
    # apr_001 (seeded) is already pending for usr_cand_001 / .NET Microservices.
    with pytest.raises(IntegrityError):
        async with pg_session.begin_nested():
            pg_session.add(_approval("apr_dup_test"))

    # A decided request doesn't block a new pending one.
    async with pg_session.begin_nested():
        pg_session.add(_approval("apr_dup_test_2", status="rejected", reviewed_at=utc_now()))


async def test_decided_approval_requires_a_review_time(client: AsyncClient, pg_session: AsyncSession):
    with pytest.raises(IntegrityError):
        async with pg_session.begin_nested():
            pg_session.add(_approval("apr_undated", requested_skill="Undated", status="approved"))


async def test_approvals_overview_keeps_every_pending_and_recent_decisions(client: AsyncClient, pg_session: AsyncSession):
    now = utc_now()
    pg_session.add_all(
        _approval(
            f"apr_hist_{i:03d}", candidate_id=f"usr_hist_{i}", requested_skill="History",
            submitted_at=now - timedelta(days=400), status="rejected", reviewed_at=now - timedelta(days=300 - i),
        )
        for i in range(250)
    )
    await pg_session.flush()

    r = await client.get("/api/admin/interviewer-approvals", headers=hdr(*ADMIN))
    assert r.status_code == 200
    approvals = r.json()["approvals"]
    pending = [a for a in approvals if a["status"] == "pending"]
    decided = [a for a in approvals if a["status"] != "pending"]
    assert len(pending) == 3  # every seeded pending request
    assert len(decided) == 200
    assert decided[0]["reviewedAt"] >= decided[-1]["reviewedAt"]  # newest first
    assert "apr_hist_000" not in {a["id"] for a in decided}  # the oldest fell off


async def test_timestamps_keep_their_wire_format(client: AsyncClient, pg_session: AsyncSession):
    r = await client.get("/api/admin/interviewer-approvals", headers=hdr(*ADMIN))
    seeded = {a["id"]: a for a in r.json()["approvals"]}
    assert seeded["apr_001"]["submittedAt"] == "2026-05-30T08:14:00.000Z"

    row = await pg_session.get(InterviewerApproval, "apr_001")
    assert row.submitted_at.tzinfo is not None
