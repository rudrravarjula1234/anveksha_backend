"""Usage logger for recording token usage to database.

Ported from ``backend/lib/agent_service/token_usage/usage_logger.py``; the
legacy ``services.token_usage_service`` dependency is replaced by the local
:mod:`app.agents.token_usage.store`.
"""

import uuid
from typing import List, Optional

from app.agents.schemas import TokenUsageCreate
from app.agents.token_usage import store


class UsageLogger:
    """Log token usage to database"""

    @staticmethod
    async def log_usage(
        agent_ids: List[str],
        model_name: str,
        orchestration_type: str,
        input_tokens: int,
        output_tokens: int,
        input_cost: float,
        output_cost: float,
        currency: str = "USD",
        interview_id: Optional[str] = None,
        user_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        """
        Log token usage to database.

        Args:
            agent_ids: List of agent IDs involved
            model_name: Model used
            orchestration_type: Type of orchestration (direct, round_robin, etc.)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            input_cost: Cost of input tokens
            output_cost: Cost of output tokens
            currency: Currency code
            interview_id: Optional interview ID
            user_id: Optional user ID
            duration_ms: Optional request duration in milliseconds

        Returns:
            request_id of the logged usage
        """
        request_id = str(uuid.uuid4())
        total_tokens = input_tokens + output_tokens
        total_cost = input_cost + output_cost

        usage = TokenUsageCreate(
            request_id=request_id,
            agent_ids=agent_ids,
            model_name=model_name,
            orchestration_type=orchestration_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            currency=currency,
            interview_id=interview_id,
            user_id=user_id,
            duration_ms=duration_ms,
        )

        await store.create_token_usage(usage)
        return request_id
