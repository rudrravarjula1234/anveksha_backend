"""Token counting utilities for different model providers.

Ported unchanged from ``backend/lib/agent_service/token_usage/token_counter.py``.
``tiktoken`` / ``anthropic`` remain optional — counting degrades to an
approximation when they are not installed.
"""

import logging

logger = logging.getLogger(__name__)


class TokenCounter:
    """Count tokens for different model providers"""

    def __init__(self, model_name: str, model_provider: str):
        """
        Initialize token counter for a specific model.

        Args:
            model_name: Model identifier (e.g., "gpt-4", "claude-3-opus")
            model_provider: Provider name (e.g., "openai", "anthropic")
        """
        self.model_name = model_name
        self.model_provider = model_provider
        self._encoder = None
        self._initialize_encoder()

    def _initialize_encoder(self):
        """Initialize the appropriate token encoder for the provider"""
        if self.model_provider == "openai":
            try:
                import tiktoken

                # Get encoding for the model
                try:
                    self._encoder = tiktoken.encoding_for_model(self.model_name)
                except KeyError:
                    # Fall back to cl100k_base for unknown models
                    self._encoder = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                logger.warning(
                    "tiktoken not installed. Token counting for OpenAI will be approximate."
                )
                self._encoder = None

        elif self.model_provider == "anthropic":
            try:
                from anthropic import Anthropic  # noqa: F401

                self._encoder = "anthropic"  # Anthropic has built-in token counting
            except ImportError:
                logger.warning(
                    "anthropic package not installed. Token counting will be approximate."
                )
                self._encoder = None

        # For other providers, we'll use approximation

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in a text string.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if not text:
            return 0

        if self.model_provider == "openai" and self._encoder:
            try:
                return len(self._encoder.encode(text))
            except Exception as e:
                logger.warning(f"Error counting tokens with tiktoken: {e}")
                return self._approximate_tokens(text)

        elif self.model_provider == "anthropic":
            # Anthropic client has count_tokens method
            # For now, we'll approximate. In production, use Anthropic client
            return self._approximate_tokens(text)

        else:
            # Approximation for other providers
            return self._approximate_tokens(text)

    def _approximate_tokens(self, text: str) -> int:
        """
        Approximate token count (rough estimate: 1 token ~ 4 characters for English).

        Args:
            text: Text to estimate tokens for

        Returns:
            Approximate number of tokens
        """
        # Rough approximation: 1 token ~ 4 characters
        # This is a very rough estimate and should be replaced with proper counting
        return len(text) // 4

    def count_messages_tokens(self, messages: list) -> int:
        """
        Count tokens in a list of messages (chat format).

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Total number of tokens
        """
        total_tokens = 0

        for message in messages:
            # Count tokens in content
            content = message.get("content", "")
            total_tokens += self.count_tokens(content)

            # Add overhead for message formatting
            # OpenAI adds ~4 tokens per message for formatting
            if self.model_provider == "openai":
                total_tokens += 4

            # Count tokens in role
            role = message.get("role", "")
            total_tokens += self.count_tokens(role)

        # Add overhead for the entire conversation
        if self.model_provider == "openai":
            total_tokens += 2  # Every conversation has a 2-token overhead

        return total_tokens
