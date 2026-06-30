"""Seed demo data for the platform dashboard.

The deterministic fallbacks never produce token-usage rows, and no
Temporal workflows run without the SDK — so without seeds the dashboard's
token and workflow tiles would always read zero. These idempotent seeds
give the admin a realistic, populated dashboard out of the box; once real
agent runs and durable workflows happen, their rows accumulate alongside.
"""

from datetime import datetime, timezone

from app.db.mongo import get_database

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed_token_usage() -> int:
    db = get_database()
    coll = db["token_usage"]
    inserted = 0
    for row in _TOKEN_USAGE_SEEDS:
        if not await coll.find_one({"request_id": row["request_id"]}):
            doc = dict(row)
            doc["currency"] = "USD"
            doc["created_at"] = _now_iso()
            await coll.insert_one(doc)
            inserted += 1
    return inserted


async def seed_workflow_runs() -> int:
    db = get_database()
    coll = db["workflow_runs"]
    inserted = 0
    for row in _WORKFLOW_RUN_SEEDS:
        if not await coll.find_one({"workflowId": row["workflowId"]}):
            doc = dict(row)
            doc["userId"] = "usr_adm_001"
            doc["startedAt"] = _now_iso()
            doc["finishedAt"] = None if doc["status"] == "running" else _now_iso()
            await coll.insert_one(doc)
            inserted += 1
    return inserted


async def seed_metrics() -> int:
    return await seed_token_usage() + await seed_workflow_runs()
