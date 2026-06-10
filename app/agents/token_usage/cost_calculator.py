"""Cost calculation utilities based on token usage and model pricing.

Ported unchanged from ``backend/lib/agent_service/token_usage/cost_calculator.py``.
"""

from typing import Any, Dict, Optional


class CostCalculator:
    """Calculate costs based on token usage and model pricing"""

    def __init__(self, pricing: Optional[Dict[str, Any]] = None):
        """
        Initialize cost calculator with pricing information.

        Args:
            pricing: Dict with 'input_tokens_per_million', 'output_tokens_per_million', 'currency'
        """
        self.pricing = pricing or {}
        self.input_rate = self.pricing.get("input_tokens_per_million", 0.0)
        self.output_rate = self.pricing.get("output_tokens_per_million", 0.0)
        self.currency = self.pricing.get("currency", "USD")

    def calculate_input_cost(self, input_tokens: int) -> float:
        """
        Calculate cost for input tokens.

        Args:
            input_tokens: Number of input tokens

        Returns:
            Cost in the specified currency
        """
        if self.input_rate == 0:
            return 0.0
        return (input_tokens / 1_000_000) * self.input_rate

    def calculate_output_cost(self, output_tokens: int) -> float:
        """
        Calculate cost for output tokens.

        Args:
            output_tokens: Number of output tokens

        Returns:
            Cost in the specified currency
        """
        if self.output_rate == 0:
            return 0.0
        return (output_tokens / 1_000_000) * self.output_rate

    def calculate_total_cost(self, input_tokens: int, output_tokens: int) -> Dict[str, Any]:
        """
        Calculate total cost breakdown.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Dict with input_cost, output_cost, total_cost, currency
        """
        input_cost = self.calculate_input_cost(input_tokens)
        output_cost = self.calculate_output_cost(output_tokens)

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6),
            "currency": self.currency,
        }
