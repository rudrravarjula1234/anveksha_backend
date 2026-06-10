"""Group Chat orchestration using autogen-agentchat 0.7.5.

Ported from ``backend/lib/agent_service/orchestrators/group_chat.py``;
AutoGen imports go through :mod:`app.agents.autogen_compat`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from app.agents.autogen_compat import (
    AssistantAgent,
    MaxMessageTermination,
    SelectorGroupChat,
    require_autogen,
)

if TYPE_CHECKING:
    from app.agents.schemas import StreamEvent
    from app.agents.streaming.stream_handler import StreamHandler

logger = logging.getLogger(__name__)


class GroupChatOrchestrator:
    """
    Group Chat orchestrator - dynamic speaker selection.

    Uses autogen-agentchat 0.7.5 SelectorGroupChat.
    Agents discuss freely with model-based speaker selection.
    """

    def __init__(
        self,
        agents: List[AssistantAgent],
        model_clients: List[Any],
        max_rounds: int = 10,
    ):
        """
        Initialize group chat orchestrator.

        Args:
            agents: List of AssistantAgent instances
            model_clients: List of model clients (one per agent)
            max_rounds: Maximum conversation rounds
        """
        require_autogen()
        self.agents = agents
        self.model_clients = model_clients
        self.max_rounds = max_rounds
        self.speaker_selection_method = "auto"  # Default

    def setup_group_chat(self, speaker_selection_method: str = "auto"):
        """
        Configure group chat settings.

        Args:
            speaker_selection_method: Selection method (auto, round_robin, etc.)
        """
        self.speaker_selection_method = speaker_selection_method

    async def run(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run group chat orchestration.

        Args:
            user_input: Initial user input
            context: Optional context

        Returns:
            Dict with final response and conversation history
        """
        logger.info(f"Starting group chat with {len(self.agents)} agents")

        # Create termination condition
        termination = MaxMessageTermination(max_messages=self.max_rounds * len(self.agents))

        # Create SelectorGroupChat team
        # The model will select next speaker based on conversation context
        team = SelectorGroupChat(
            participants=self.agents,
            model_client=self.model_clients[0],  # Use first agent's model for selection
            termination_condition=termination,
        )

        # Add MCP context if provided
        initial_message = user_input
        if context and context.get("mcp_results"):
            mcp_context = self._format_mcp_context(context["mcp_results"])
            initial_message = f"{mcp_context}\n\n{user_input}"

        # Run the team
        result = await team.run(task=initial_message)

        # Extract messages
        messages = []
        if hasattr(result, "messages"):
            messages = result.messages

        # Get final response (last message's content)
        final_response = ""
        if messages:
            last_msg = messages[-1]
            final_response = getattr(last_msg, "content", str(last_msg))

        return {
            "final_response": final_response,
            "conversation_history": [self._message_to_dict(msg) for msg in messages],
            "num_rounds": len(messages) // len(self.agents) if self.agents else 0,
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
        Run group chat with streaming output.

        Args:
            user_input: Initial user input
            stream_handler: Handler for stream events
            context: Optional context

        Yields:
            StreamEvent for each message
        """
        from app.agents.schemas import StreamEvent, StreamEventType

        logger.info(f"Starting streaming group chat with {len(self.agents)} agents")

        # Create termination condition
        termination = MaxMessageTermination(max_messages=self.max_rounds * len(self.agents))

        # Filter out None model clients (from human agents)
        valid_model_clients = [mc for mc in self.model_clients if mc is not None]
        if not valid_model_clients:
            raise ValueError("At least one model client is required for group chat")

        # Create SelectorGroupChat team
        team = SelectorGroupChat(
            participants=self.agents,
            model_client=valid_model_clients[0],
            termination_condition=termination,
        )

        # Add MCP context if provided
        initial_message = user_input
        if context and context.get("mcp_results"):
            mcp_context = self._format_mcp_context(context["mcp_results"])
            initial_message = f"{mcp_context}\n\n{user_input}"

        # Use run_stream if available (autogen 0.7.5+)
        if hasattr(team, "run_stream"):
            async for message in team.run_stream(task=initial_message):
                # Convert to StreamEvent
                if hasattr(message, "content"):
                    event = StreamEvent(
                        event_type=StreamEventType.MESSAGE,
                        content=getattr(message, "content", str(message)),
                        source=getattr(message, "source", "unknown"),
                        metadata={"role": getattr(message, "role", "assistant")},
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
                    metadata={"role": getattr(msg, "role", "assistant")},
                )
                await stream_handler.emit(event)
                yield event

    def _message_to_dict(self, message) -> Dict[str, Any]:
        """Convert message object to dict"""
        return {
            "source": getattr(message, "source", "unknown"),
            "content": getattr(message, "content", str(message)),
            "role": getattr(message, "role", "assistant"),
        }

    def _format_mcp_context(self, mcp_results: List[Dict[str, Any]]) -> str:
        """Format MCP results as context"""
        if not mcp_results:
            return ""

        context_parts = ["[Available reference documentation]:"]
        for result in mcp_results:
            server_name = result.get("server_name", "Unknown")
            results = result.get("results", [])
            for item in results:
                title = item.get("title", "")
                context_parts.append(f"\n- {server_name}: {title}")

        return "\n".join(context_parts)
