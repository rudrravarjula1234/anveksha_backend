"""Round Robin orchestration using autogen-agentchat 0.7.5.

Ported from ``backend/lib/agent_service/orchestrators/round_robin.py``;
AutoGen imports go through :mod:`app.agents.autogen_compat`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from app.agents.autogen_compat import (
    AssistantAgent,
    MaxMessageTermination,
    RoundRobinGroupChat,
    require_autogen,
)

if TYPE_CHECKING:
    from app.agents.schemas import StreamEvent
    from app.agents.streaming.stream_handler import StreamHandler

logger = logging.getLogger(__name__)


class RoundRobinOrchestrator:
    """
    Round Robin orchestrator - agents take turns in sequence.

    Uses autogen-agentchat 0.7.5 RoundRobinGroupChat.
    Each agent gets a turn to respond, then the next agent, etc.
    """

    def __init__(
        self,
        agents: List[AssistantAgent],
        model_clients: List[Any],
        max_rounds: int = 3,
    ):
        """
        Initialize round robin orchestrator.

        Args:
            agents: List of AssistantAgent instances (in order of rotation)
            model_clients: List of model clients (one per agent)
            max_rounds: Number of complete rounds through all agents
        """
        require_autogen()
        self.agents = agents
        self.model_clients = model_clients
        self.max_rounds = max_rounds

    async def run(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run round robin orchestration.

        Args:
            user_input: Initial user input/topic
            context: Optional context (MCP results, etc.)

        Returns:
            Dict with responses from all agents and conversation history
        """
        logger.info(
            f"Starting round robin with {len(self.agents)} agents, {self.max_rounds} rounds"
        )

        # Calculate max total messages (agents * rounds * 2 for responses)
        max_messages = len(self.agents) * self.max_rounds * 2

        # Create termination condition
        termination = MaxMessageTermination(max_messages=max_messages)

        # Create RoundRobinGroupChat team
        team = RoundRobinGroupChat(
            participants=self.agents,
            termination_condition=termination,
        )

        # Add MCP context to initial message if provided
        initial_message = user_input
        if context and context.get("mcp_results"):
            mcp_context = self._format_mcp_context(context["mcp_results"])
            initial_message = f"{mcp_context}\n\n{user_input}"

        # Run the team
        result = await team.run(task=initial_message)

        # Extract conversation messages
        messages = []
        if hasattr(result, "messages"):
            messages = result.messages

        # Build response
        return {
            "final_response": self._compile_final_response(messages),
            "conversation_history": [self._message_to_dict(msg) for msg in messages],
            "num_rounds": self.max_rounds,
            "participants": [agent.name for agent in self.agents],
            "stop_reason": getattr(result, "stop_reason", "max_messages"),
        }

    async def run_stream(
        self,
        user_input: str,
        stream_handler: "StreamHandler",
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator["StreamEvent", None]:
        """
        Run round robin with streaming output.

        Args:
            user_input: Initial user input
            stream_handler: Handler for stream events
            context: Optional context

        Yields:
            StreamEvent for each message
        """
        from app.agents.schemas import StreamEvent, StreamEventType

        logger.info(f"Starting streaming round robin with {len(self.agents)} agents")

        max_messages = len(self.agents) * self.max_rounds * 2
        termination = MaxMessageTermination(max_messages=max_messages)

        team = RoundRobinGroupChat(
            participants=self.agents,
            termination_condition=termination,
        )

        initial_message = user_input
        if context and context.get("mcp_results"):
            mcp_context = self._format_mcp_context(context["mcp_results"])
            initial_message = f"{mcp_context}\n\n{user_input}"

        # Use run_stream if available
        if hasattr(team, "run_stream"):
            async for message in team.run_stream(task=initial_message):
                if hasattr(message, "content"):
                    event = StreamEvent(
                        event_type=StreamEventType.MESSAGE,
                        content=getattr(message, "content", str(message)),
                        source=getattr(message, "source", "unknown"),
                    )
                    await stream_handler.emit(event)
                    yield event
        else:
            # Fallback to non-streaming
            result = await team.run(task=initial_message)
            messages = getattr(result, "messages", [])

            for msg in messages:
                event = StreamEvent(
                    event_type=StreamEventType.MESSAGE,
                    content=getattr(msg, "content", str(msg)),
                    source=getattr(msg, "source", "unknown"),
                )
                await stream_handler.emit(event)
                yield event

    def _message_to_dict(self, message) -> Dict[str, Any]:
        """Convert message object to dict"""
        return {
            "source": getattr(message, "source", "unknown"),
            "content": getattr(message, "content", str(message)),
        }

    def _compile_final_response(self, messages: List) -> str:
        """Compile all messages into a final summary"""
        if not messages:
            return "No responses generated"

        summary_parts = ["Round Robin Interview Summary:\n"]

        for idx, msg in enumerate(messages):
            source = getattr(msg, "source", "Unknown")
            content = getattr(msg, "content", str(msg))
            summary_parts.append(f"\n[{idx + 1}] {source}:")
            summary_parts.append(f"{content}\n")

        return "\n".join(summary_parts)

    def _format_mcp_context(self, mcp_results: List[Dict[str, Any]]) -> str:
        """Format MCP results as context"""
        if not mcp_results:
            return ""

        context_parts = ["[Reference documentation]:"]
        for result in mcp_results:
            server_name = result.get("server_name", "Unknown")
            results = result.get("results", [])
            for item in results:
                title = item.get("title", "")
                context_parts.append(f"\n- {server_name}: {title}")

        return "\n".join(context_parts)
