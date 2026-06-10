"""Base provider interface for autogen 0.7.5.

Ported from ``backend/lib/agent_service/providers/base.py``; the AutoGen
import now goes through :mod:`app.agents.autogen_compat` so the module is
importable without the optional dependencies (annotations are deferred via
``from __future__ import annotations``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from app.agents.autogen_compat import AssistantAgent  # noqa: F401 (re-export for typing)


class BaseModelProvider(ABC):
    """
    Abstract base class for model providers using autogen 0.7.5 API.

    All providers must implement these methods to create agents
    and make direct calls.
    """

    @abstractmethod
    async def create_agent(
        self,
        name: str,
        system_message: str,
        **kwargs,
    ) -> AssistantAgent:
        """
        Create an Autogen AssistantAgent.

        Args:
            name: Agent name
            system_message: System message/prompt
            **kwargs: Additional configuration

        Returns:
            AssistantAgent instance
        """
        pass

    @abstractmethod
    async def direct_call(
        self,
        user_input: str,
        system_message: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Make a direct call to the model without creating an agent.

        Args:
            user_input: User message
            system_message: Optional system message
            **kwargs: Additional parameters

        Returns:
            Model response text
        """
        pass

    async def direct_call_stream(
        self,
        user_input: str,
        system_message: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Make a streaming direct call to the model.

        Default implementation falls back to non-streaming call.
        Override in subclasses to enable true streaming.

        Args:
            user_input: User message
            system_message: Optional system message
            **kwargs: Additional parameters

        Yields:
            Token strings as they are generated
        """
        # Default: fall back to non-streaming
        response = await self.direct_call(user_input, system_message, **kwargs)
        yield response
