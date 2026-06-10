"""Mongo persistence for token usage records.

Replacement for the legacy ``services/token_usage_service.py`` — same
function contracts, but rows go to the ``token_usage`` collection of the
new backend via :func:`app.db.mongo.get_database`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.agents.schemas import TokenUsage, TokenUsageCreate, TokenUsageStats
from app.db.mongo import get_database

COLLECTION = "token_usage"


def _to_model(doc: Dict[str, Any]) -> TokenUsage:
    doc = dict(doc)
    object_id = doc.pop("_id", None)
    doc.setdefault("id", str(object_id))
    return TokenUsage(**doc)


async def create_token_usage(usage: TokenUsageCreate) -> TokenUsage:
    """Create a new token usage record"""
    db = get_database()
    data = usage.model_dump()
    data["created_at"] = datetime.now(timezone.utc)

    result = await db[COLLECTION].insert_one(data)
    created = await db[COLLECTION].find_one({"_id": result.inserted_id})
    return _to_model(created)


async def get_token_usage(request_id: str) -> Optional[TokenUsage]:
    """Get token usage by request ID"""
    db = get_database()
    doc = await db[COLLECTION].find_one({"request_id": request_id})
    return _to_model(doc) if doc else None


async def list_recent(limit: int = 50) -> List[TokenUsage]:
    """Most recent usage rows, newest first (new in the port — feeds the API)."""
    db = get_database()
    cursor = db[COLLECTION].find({}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return [_to_model(doc) for doc in items]


def _date_range_query(start_date: Optional[date], end_date: Optional[date]) -> Dict[str, Any]:
    date_query: Dict[str, Any] = {}
    if start_date:
        date_query["$gte"] = datetime.combine(start_date, datetime.min.time())
    if end_date:
        date_query["$lte"] = datetime.combine(end_date, datetime.max.time())
    return date_query


async def get_usage_by_agent(
    agent_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[TokenUsage]:
    """Get token usage for a specific agent"""
    db = get_database()
    query: Dict[str, Any] = {"agent_ids": agent_id}
    if start_date or end_date:
        query["created_at"] = _date_range_query(start_date, end_date)

    cursor = db[COLLECTION].find(query).sort("created_at", -1)
    items = await cursor.to_list(length=None)
    return [_to_model(doc) for doc in items]


async def get_usage_by_model(
    model_name: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[TokenUsage]:
    """Get token usage for a specific model"""
    db = get_database()
    query: Dict[str, Any] = {"model_name": model_name}
    if start_date or end_date:
        query["created_at"] = _date_range_query(start_date, end_date)

    cursor = db[COLLECTION].find(query).sort("created_at", -1)
    items = await cursor.to_list(length=None)
    return [_to_model(doc) for doc in items]


async def get_usage_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    model_name: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> TokenUsageStats:
    """Get aggregated token usage statistics"""
    db = get_database()
    query: Dict[str, Any] = {}

    if start_date or end_date:
        query["created_at"] = _date_range_query(start_date, end_date)
    if model_name:
        query["model_name"] = model_name
    if agent_id:
        query["agent_ids"] = agent_id

    # Aggregate stats
    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": None,
                "total_requests": {"$sum": 1},
                "total_input_tokens": {"$sum": "$input_tokens"},
                "total_output_tokens": {"$sum": "$output_tokens"},
                "total_tokens": {"$sum": "$total_tokens"},
                "total_cost": {"$sum": "$total_cost"},
            }
        },
    ]

    result = await db[COLLECTION].aggregate(pipeline).to_list(length=1)

    if not result:
        return TokenUsageStats(
            total_requests=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_tokens=0,
            total_cost=0.0,
            currency="USD",
            average_tokens_per_request=0.0,
            average_cost_per_request=0.0,
        )

    stats = result[0]
    total_requests = stats["total_requests"]

    return TokenUsageStats(
        total_requests=total_requests,
        total_input_tokens=stats["total_input_tokens"],
        total_output_tokens=stats["total_output_tokens"],
        total_tokens=stats["total_tokens"],
        total_cost=stats["total_cost"],
        currency="USD",
        average_tokens_per_request=(
            stats["total_tokens"] / total_requests if total_requests > 0 else 0.0
        ),
        average_cost_per_request=(
            stats["total_cost"] / total_requests if total_requests > 0 else 0.0
        ),
    )
