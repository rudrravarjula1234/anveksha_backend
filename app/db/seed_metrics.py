"""Seed demo data for the platform dashboard.

The deterministic fallbacks never produce token-usage rows, and no
Temporal workflows run without the SDK — so without seeds the dashboard's
token and workflow tiles would always read zero. These idempotent seeds
give the admin a realistic, populated dashboard out of the box; once real
agent runs and durable workflows happen, their rows accumulate alongside.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import token_usage_id
from app.models.token_usage import TokenUsage, TokenUsageAgentId
from app.models.workflow import WorkflowRun

# Mirrors a week of mixed agent traffic across the seeded models.
_TOKEN_USAGE_SEEDS = [
    {"request_id": "tu_seed_1", "model_name": "gpt-4o", "agent_ids": ["gray_analyzer"],
     "orchestration_type": "direct", "input_tokens": 1820, "output_tokens": 640,
     "total_tokens": 2460, "input_cost": 0.0091, "output_cost": 0.0064, "total_cost": 0.0155},
    {"request_id": "tu_seed_2", "model_name": "gpt-4o", "agent_ids": ["report_generator"],
     "orchestration_type": "direct", "input_tokens": 3120, "output_tokens": 1180,
     "total_tokens": 4300, "input_cost": 0.0156, "output_cost": 0.0118, "total_cost": 0.0274},
    {"request_id": "tu_seed_3", "model_name": "claude-3-5-sonnet", "agent_ids": ["gap_analyzer"],
     "orchestration_type": "direct", "input_tokens": 2040, "output_tokens": 880,
     "total_tokens": 2920, "input_cost": 0.0061, "output_cost": 0.0132, "total_cost": 0.0193},
    {"request_id": "tu_seed_4", "model_name": "claude-3-5-sonnet", "agent_ids": ["candidate_chat"],
     "orchestration_type": "direct", "input_tokens": 1450, "output_tokens": 520,
     "total_tokens": 1970, "input_cost": 0.0044, "output_cost": 0.0078, "total_cost": 0.0122},
    {"request_id": "tu_seed_5", "model_name": "gemini-2.0-flash", "agent_ids": ["interviewer_brief"],
     "orchestration_type": "direct", "input_tokens": 980, "output_tokens": 360,
     "total_tokens": 1340, "input_cost": 0.0001, "output_cost": 0.0001, "total_cost": 0.0002},
    {"request_id": "tu_seed_6", "model_name": "gemini-2.0-flash", "agent_ids": ["candidate_search"],
     "orchestration_type": "direct", "input_tokens": 1260, "output_tokens": 410,
     "total_tokens": 1670, "input_cost": 0.0001, "output_cost": 0.0002, "total_cost": 0.0003},
]

# A spread of workflow runs across terminal + running states.
_WORKFLOW_RUN_SEEDS = [
    {"workflowId": "agent-report_generator-seed01", "agentId": "report_generator", "status": "completed"},
    {"workflowId": "agent-report_generator-seed02", "agentId": "report_generator", "status": "completed"},
    {"workflowId": "agent-gray_analyzer-seed03", "agentId": "gray_analyzer", "status": "completed"},
    {"workflowId": "agent-gap_analyzer-seed04", "agentId": "gap_analyzer", "status": "completed"},
    {"workflowId": "agent-candidate_search-seed05", "agentId": "candidate_search", "status": "running"},
    {"workflowId": "agent-report_generator-seed06", "agentId": "report_generator", "status": "failed"},
]


async def seed_token_usage(db: AsyncSession) -> int:
    inserted = 0
    for row in _TOKEN_USAGE_SEEDS:
        stmt = select(TokenUsage).where(TokenUsage.request_id == row["request_id"])
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            continue
        usage = TokenUsage(
            id=token_usage_id(),
            request_id=row["request_id"],
            model_name=row["model_name"],
            orchestration_type=row["orchestration_type"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            input_cost=row["input_cost"],
            output_cost=row["output_cost"],
            total_cost=row["total_cost"],
            currency="USD",
        )
        usage.agent_ids = [TokenUsageAgentId(agent_id=a) for a in row["agent_ids"]]
        db.add(usage)
        inserted += 1
    if inserted:
        await db.flush()
    return inserted


async def seed_workflow_runs(db: AsyncSession) -> int:
    inserted = 0
    for row in _WORKFLOW_RUN_SEEDS:
        if await db.get(WorkflowRun, row["workflowId"]) is not None:
            continue
        finished_at = None if row["status"] == "running" else datetime.now(timezone.utc)
        db.add(
            WorkflowRun(
                workflow_id=row["workflowId"],
                agent_id=row["agentId"],
                user_id="usr_adm_001",
                status=row["status"],
                finished_at=finished_at,
            )
        )
        inserted += 1
    if inserted:
        await db.flush()
    return inserted


async def seed_metrics(db: AsyncSession) -> int:
    return await seed_token_usage(db) + await seed_workflow_runs(db)
