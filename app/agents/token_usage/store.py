"""Token usage persistence — rows go to ``token_usage``/
``token_usage_agent_ids`` (see ``app.models.token_usage``).

Each function takes an optional ``db: AsyncSession``; when omitted (e.g.
called from a Temporal worker activity with no request cycle), a
short-lived session is opened and committed internally.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import TokenUsage, TokenUsageCreate, TokenUsageStats
from app.core.ids import token_usage_id
from app.db.session import session_scope
from app.models.token_usage import TokenUsage as TokenUsageModel
from app.models.token_usage import TokenUsageAgentId as TokenUsageAgentIdModel
from app.models.token_usage import TokenUsageModelTotals as TokenUsageModelTotalsModel


def _to_schema(row: TokenUsageModel) -> TokenUsage:
    return TokenUsage(
        id=row.id,
        request_id=row.request_id,
        agent_ids=[a.agent_id for a in row.agent_ids],
        model_name=row.model_name,
        orchestration_type=row.orchestration_type,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        total_tokens=row.total_tokens,
        input_cost=row.input_cost,
        output_cost=row.output_cost,
        total_cost=row.total_cost,
        currency=row.currency,
        interview_id=row.interview_id,
        user_id=row.user_id,
        duration_ms=row.duration_ms,
        created_at=row.created_at,
    )


async def create_token_usage(usage: TokenUsageCreate, db: Optional[AsyncSession] = None) -> TokenUsage:
    """Create a new token usage record"""
    row = TokenUsageModel(
        id=token_usage_id(),
        request_id=usage.request_id,
        model_name=usage.model_name,
        orchestration_type=usage.orchestration_type,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        input_cost=usage.input_cost,
        output_cost=usage.output_cost,
        total_cost=usage.total_cost,
        currency=usage.currency,
        interview_id=usage.interview_id,
        user_id=usage.user_id,
        duration_ms=usage.duration_ms,
    )
    row.agent_ids = [TokenUsageAgentIdModel(agent_id=a) for a in usage.agent_ids]

    async with session_scope(db, write=True) as session:
        session.add(row)
    return _to_schema(row)


async def get_token_usage(request_id: str, db: Optional[AsyncSession] = None) -> Optional[TokenUsage]:
    """Get token usage by request ID"""
    stmt = select(TokenUsageModel).where(TokenUsageModel.request_id == request_id)
    async with session_scope(db) as session:
        row = (await session.execute(stmt)).scalar_one_or_none()
    return _to_schema(row) if row is not None else None


async def list_recent(limit: int = 50, db: Optional[AsyncSession] = None) -> List[TokenUsage]:
    """Most recent usage rows, newest first (new in the port — feeds the API)."""
    stmt = select(TokenUsageModel).order_by(TokenUsageModel.created_at.desc()).limit(limit)
    async with session_scope(db) as session:
        rows = (await session.execute(stmt)).scalars().all()
    return [_to_schema(r) for r in rows]


def _apply_date_range(stmt: Select, start_date: Optional[date], end_date: Optional[date]) -> Select:
    if start_date:
        stmt = stmt.where(
            TokenUsageModel.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        )
    if end_date:
        stmt = stmt.where(
            TokenUsageModel.created_at <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        )
    return stmt


async def get_usage_by_agent(
    agent_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Optional[AsyncSession] = None,
) -> List[TokenUsage]:
    """Get token usage for a specific agent"""
    stmt = (
        select(TokenUsageModel)
        .join(TokenUsageAgentIdModel, TokenUsageAgentIdModel.token_usage_id == TokenUsageModel.id)
        .where(TokenUsageAgentIdModel.agent_id == agent_id)
    )
    stmt = _apply_date_range(stmt, start_date, end_date).order_by(TokenUsageModel.created_at.desc())
    async with session_scope(db) as session:
        rows = (await session.execute(stmt)).scalars().all()
    return [_to_schema(r) for r in rows]


async def get_usage_by_model(
    model_name: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Optional[AsyncSession] = None,
) -> List[TokenUsage]:
    """Get token usage for a specific model"""
    stmt = select(TokenUsageModel).where(TokenUsageModel.model_name == model_name)
    stmt = _apply_date_range(stmt, start_date, end_date).order_by(TokenUsageModel.created_at.desc())
    async with session_scope(db) as session:
        rows = (await session.execute(stmt)).scalars().all()
    return [_to_schema(r) for r in rows]


async def get_usage_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    model_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> TokenUsageStats:
    """Get aggregated token usage statistics — a real SQL aggregate, not a
    Python-side loop over every matching row. With no date range or agent
    filter the answer is already in token_usage_model_totals (trigger-
    maintained), so the ledger isn't scanned at all."""
    if not (start_date or end_date or agent_id):
        stmt = select(
            func.coalesce(func.sum(TokenUsageModelTotalsModel.requests), 0),
            func.coalesce(func.sum(TokenUsageModelTotalsModel.input_tokens), 0),
            func.coalesce(func.sum(TokenUsageModelTotalsModel.output_tokens), 0),
            func.coalesce(func.sum(TokenUsageModelTotalsModel.total_tokens), 0),
            func.coalesce(func.sum(TokenUsageModelTotalsModel.total_cost), 0.0),
        )
        if model_name:
            stmt = stmt.where(TokenUsageModelTotalsModel.model_name == model_name)
        return await _stats_from(stmt, db)
    stmt = select(
        func.count(TokenUsageModel.id),
        func.coalesce(func.sum(TokenUsageModel.input_tokens), 0),
        func.coalesce(func.sum(TokenUsageModel.output_tokens), 0),
        func.coalesce(func.sum(TokenUsageModel.total_tokens), 0),
        func.coalesce(func.sum(TokenUsageModel.total_cost), 0.0),
    )
    if agent_id:
        stmt = stmt.join(
            TokenUsageAgentIdModel, TokenUsageAgentIdModel.token_usage_id == TokenUsageModel.id
        ).where(TokenUsageAgentIdModel.agent_id == agent_id)
    if model_name:
        stmt = stmt.where(TokenUsageModel.model_name == model_name)
    stmt = _apply_date_range(stmt, start_date, end_date)
    return await _stats_from(stmt, db)


async def _stats_from(stmt: Select, db: Optional[AsyncSession]) -> TokenUsageStats:
    async with session_scope(db) as session:
        total_requests, total_input, total_output, total_tokens, total_cost = (await session.execute(stmt)).one()

    total_requests, total_input, total_output, total_tokens = (
        int(total_requests), int(total_input), int(total_output), int(total_tokens)
    )
    total_cost = float(total_cost)
    return TokenUsageStats(
        total_requests=total_requests,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_tokens,
        total_cost=total_cost,
        currency="USD",
        average_tokens_per_request=(total_tokens / total_requests if total_requests > 0 else 0.0),
        average_cost_per_request=(total_cost / total_requests if total_requests > 0 else 0.0),
    )
