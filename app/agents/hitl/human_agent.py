"""Human Actor Agent for Human-in-the-Loop orchestration.

Ported from ``backend/lib/agent_service/hitl/human_agent.py``. AutoGen
imports are routed through :mod:`app.agents.autogen_compat`; when AutoGen is
missing, ``BaseChatAgent`` degrades to ``object`` so this module still
imports — instantiating an agent then raises a clear 503-style error via
``require_autogen()``.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from app.agents.autogen_compat import (
    BaseChatAgent,
    CancellationToken,
    ChatMessage,
    Response,
    TextMessage,
    require_autogen,
)
from app.agents.schemas import HumanInputMode, HumanInputRequest

from .handler import HumanInputHandler

logger = logging.getLogger(__name__)


class HumanActorAgent(BaseChatAgent):
    """
    An agent that represents a human participant in orchestration.

    When this agent's turn comes in the conversation, it pauses
    execution and waits for real human input via the HumanInputHandler.

    This allows humans to participate naturally as actors in
    multi-agent orchestrations.

    Usage:
        handler = HumanInputHandler()
        human_agent = HumanActorAgent(
            name="Human_Expert",
            handler=handler,
            description="Human domain expert who reviews and approves decisions"
        )

        # Add to orchestration with other AI agents
        team = RoundRobinGroupChat(participants=[ai_agent, human_agent, ...])
    """

    def __init__(
        self,
        name: str,
        handler: HumanInputHandler,
        description: str = "Human participant",
        input_mode: HumanInputMode = HumanInputMode.ON_DEMAND,
        prompt_template: Optional[str] = None,
        timeout_seconds: int = 300,
        **kwargs,
    ):
        """
        Initialize a Human Actor Agent.

        Args:
            name: Agent name (displayed in conversation)
            handler: HumanInputHandler for managing input requests
            description: Description of human's role
            input_mode: When to request human input
            prompt_template: Template for prompting human (uses {context} placeholder)
            timeout_seconds: Timeout for human responses
        """
        require_autogen()
        super().__init__(name=name, description=description)
        self._handler = handler
        self._input_mode = input_mode
        self._timeout_seconds = timeout_seconds
        self._prompt_template = prompt_template or (
            "You are acting as '{name}' in this conversation.\n\n"
            "Current context:\n{context}\n\n"
            "Please provide your input:"
        )
        self._message_count = 0
        logger.info(f"Human Actor Agent created: {name}")

    @property
    def produced_message_types(self) -> Sequence[type[ChatMessage]]:
        """Message types this agent can produce"""
        return [TextMessage]

    async def on_messages(
        self,
        messages: Sequence[ChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """
        Handle incoming messages and request human input.

        Args:
            messages: Incoming messages from other agents
            cancellation_token: Token for cancellation

        Returns:
            Human's response wrapped in a Response object
        """
        self._message_count += 1

        # Build context from messages
        context = self._build_context(messages)

        # Check if we should request human input based on mode
        if not self._should_request_input():
            # In NEVER mode, provide a default response
            msg = TextMessage(
                content="[Human input not required at this time]",
                source=self.name,
            )
            return Response(chat_message=msg, inner_messages=None)

        # Create human input request
        request = HumanInputRequest(
            context=context,
            prompt_for_human=self._format_prompt(context),
            agent_name=self.name,
            timeout_seconds=self._timeout_seconds,
            metadata={
                "message_count": self._message_count,
                "input_mode": self._input_mode.value,
            },
        )

        # Log and wait for human input
        logger.info(f"Requesting human input for {self.name}")

        try:
            response = await self._handler.request_input(request)

            # Handle different response actions
            if response.action == "abort":
                msg = TextMessage(
                    content="[Human requested to abort the conversation]",
                    source=self.name,
                )
                return Response(chat_message=msg, inner_messages=None)
            elif response.action == "timeout":
                msg = TextMessage(
                    content="[Human input timed out - proceeding with default]",
                    source=self.name,
                )
                return Response(chat_message=msg, inner_messages=None)
            elif response.action == "cancelled":
                msg = TextMessage(
                    content="[Human input request was cancelled]",
                    source=self.name,
                )
                return Response(chat_message=msg, inner_messages=None)
            else:
                # Normal response
                msg = TextMessage(
                    content=response.content,
                    source=self.name,
                )
                return Response(chat_message=msg, inner_messages=None)

        except Exception as e:
            logger.error(f"Error getting human input: {e}")
            msg = TextMessage(
                content=f"[Error requesting human input: {str(e)}]",
                source=self.name,
            )
            return Response(chat_message=msg, inner_messages=None)

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        """Reset agent state"""
        self._message_count = 0
        logger.debug(f"Human Actor Agent reset: {self.name}")

    def _should_request_input(self) -> bool:
        """Determine if human input should be requested based on mode"""
        if self._input_mode == HumanInputMode.NEVER:
            return False
        elif self._input_mode == HumanInputMode.EVERY_MESSAGE:
            return True
        elif self._input_mode == HumanInputMode.ON_DEMAND:
            # Always request in on-demand mode (agent is explicitly called)
            return True
        elif self._input_mode == HumanInputMode.STEP_APPROVAL:
            return True
        return True

    def _build_context(self, messages: Sequence[ChatMessage]) -> str:
        """Build context string from recent messages"""
        context_parts = []

        # Take last 10 messages for context
        recent_messages = list(messages)[-10:]

        for msg in recent_messages:
            source = getattr(msg, "source", "unknown")
            content = getattr(msg, "content", str(msg))
            context_parts.append(f"[{source}]: {content}")

        return "\n\n".join(context_parts)

    def _format_prompt(self, context: str) -> str:
        """Format the prompt template with context"""
        return self._prompt_template.format(
            name=self.name,
            context=context,
        )


class HumanApprovalAgent(HumanActorAgent):
    """
    Specialized human agent for approval workflows.

    Provides structured approve/reject/modify options.
    """

    def __init__(
        self,
        name: str = "Human_Approver",
        handler: Optional[HumanInputHandler] = None,
        approval_prompt: str = "Please review and approve, reject, or modify:",
        **kwargs,
    ):
        prompt_template = (
            "=== APPROVAL REQUIRED ===\n\n"
            "{context}\n\n"
            f"{approval_prompt}\n\n"
            "Options:\n"
            "1. APPROVE - Accept as is\n"
            "2. REJECT - Reject with reason\n"
            "3. MODIFY - Provide modifications\n"
        )

        super().__init__(
            name=name,
            handler=handler or HumanInputHandler(),
            description="Human approver for workflow steps",
            input_mode=HumanInputMode.STEP_APPROVAL,
            prompt_template=prompt_template,
            **kwargs,
        )
        self._approval_options = ["APPROVE", "REJECT", "MODIFY"]

    async def on_messages(
        self,
        messages: Sequence[ChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """Handle approval request with structured options"""
        context = self._build_context(messages)

        request = HumanInputRequest(
            context=context,
            prompt_for_human=self._format_prompt(context),
            agent_name=self.name,
            options=self._approval_options,
            timeout_seconds=self._timeout_seconds,
            metadata={"type": "approval"},
        )

        response = await self._handler.request_input(request)

        # Parse approval response
        content = response.content.strip().upper()

        if content.startswith("APPROVE"):
            msg = TextMessage(
                content="APPROVED",
                source=self.name,
            )
            return Response(chat_message=msg, inner_messages=None)
        elif content.startswith("REJECT"):
            reason = (
                response.content[6:].strip() if len(response.content) > 6 else "No reason provided"
            )
            msg = TextMessage(
                content=f"REJECTED: {reason}",
                source=self.name,
            )
            return Response(chat_message=msg, inner_messages=None)
        else:
            # Treat as modification/feedback
            msg = TextMessage(
                content=f"MODIFICATION REQUESTED: {response.content}",
                source=self.name,
            )
            return Response(chat_message=msg, inner_messages=None)
