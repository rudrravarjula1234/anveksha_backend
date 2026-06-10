"""Workflow + hierarchical orchestrators using autogen-agentchat 0.7.5.

Ported from ``backend/lib/agent_service/orchestrators/workflow.py``;
AutoGen imports go through :mod:`app.agents.autogen_compat`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from app.agents.autogen_compat import (
    AssistantAgent,
    MaxMessageTermination,
    RoundRobinGroupChat,
    SelectorGroupChat,
    require_autogen,
)

if TYPE_CHECKING:
    from app.agents.schemas import StreamEvent
    from app.agents.streaming.stream_handler import StreamHandler

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """
    Workflow orchestrator - sequential multi-step pipeline.

    In autogen 0.7.5, workflows are implemented as sequential round-robin
    with specific agents assigned to each step.
    """

    def __init__(
        self,
        agents: List[AssistantAgent],
        model_clients: List[Any],
        workflow_steps: List[Dict[str, Any]],
    ):
        """
        Initialize workflow orchestrator.

        Args:
            agents: List of AssistantAgent instances
            model_clients: List of model clients (one per agent)
            workflow_steps: List of workflow step definitions
        """
        require_autogen()
        self.agents = agents
        self.model_clients = model_clients
        self.workflow_steps = workflow_steps
        self.step_results = []

    async def run(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run workflow orchestration.

        Args:
            user_input: Initial context
            context: Optional additional context

        Returns:
            Dict with step results
        """
        logger.info(f"Starting workflow with {len(self.workflow_steps)} steps")

        cumulative_context = f"Context: {user_input}\n\n"

        # Execute each workflow step
        for step_idx, step_config in enumerate(self.workflow_steps):
            step_name = step_config.get("step_name", f"Step {step_idx + 1}")
            agent_index = step_config.get("agent_index", 0)
            description = step_config.get("description", "")
            max_turns = step_config.get("max_turns", 5)

            logger.info(f"Executing step {step_idx + 1}: {step_name}")

            # Get agent for this step
            agent = self.agents[agent_index]

            # Build step message
            step_message = f"=== {step_name} ===\n"
            if description:
                step_message += f"Objective: {description}\n\n"
            step_message += cumulative_context
            step_message += f"\nPlease proceed with {step_name}:"

            # Create a single-agent team for this step
            termination = MaxMessageTermination(max_messages=max_turns)
            team = RoundRobinGroupChat(
                participants=[agent],
                termination_condition=termination,
            )

            # Execute step
            result = await team.run(task=step_message)

            # Extract response
            step_response = ""
            if hasattr(result, "messages") and result.messages:
                last_msg = result.messages[-1]
                step_response = getattr(last_msg, "content", str(last_msg))

            step_result = {
                "step_number": step_idx + 1,
                "step_name": step_name,
                "agent": agent.name,
                "description": description,
                "response": step_response,
            }

            self.step_results.append(step_result)

            # Update cumulative context
            cumulative_context += f"\n{step_name}: {step_response[:300]}...\n"

        # Generate summary
        final_response = self._generate_summary()

        return {
            "final_response": final_response,
            "step_results": self.step_results,
            "num_steps": len(self.workflow_steps),
            "workflow_complete": True,
            "participants": [
                self.agents[step["agent_index"]].name for step in self.workflow_steps
            ],
        }

    async def run_stream(
        self,
        user_input: str,
        stream_handler: "StreamHandler",
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator["StreamEvent", None]:
        """
        Run workflow with streaming output.

        Yields events for each step, supporting human-in-the-loop approval.

        Args:
            user_input: Initial context
            stream_handler: Handler for stream events
            context: Optional additional context

        Yields:
            StreamEvent for each step and message
        """
        from app.agents.schemas import StreamEvent, StreamEventType

        logger.info(f"Starting streaming workflow with {len(self.workflow_steps)} steps")

        cumulative_context = f"Context: {user_input}\n\n"

        for step_idx, step_config in enumerate(self.workflow_steps):
            step_name = step_config.get("step_name", f"Step {step_idx + 1}")
            agent_index = step_config.get("agent_index", 0)
            description = step_config.get("description", "")
            max_turns = step_config.get("max_turns", 5)

            # Emit step start event
            await stream_handler.emit_status(
                f"Starting step: {step_name}",
                metadata={"step_number": step_idx + 1, "step_name": step_name},
            )
            yield StreamEvent(
                event_type=StreamEventType.STATUS,
                content=f"Starting step: {step_name}",
                metadata={"step_number": step_idx + 1},
            )

            agent = self.agents[agent_index]

            step_message = f"=== {step_name} ===\n"
            if description:
                step_message += f"Objective: {description}\n\n"
            step_message += cumulative_context
            step_message += f"\nPlease proceed with {step_name}:"

            termination = MaxMessageTermination(max_messages=max_turns)
            team = RoundRobinGroupChat(
                participants=[agent],
                termination_condition=termination,
            )

            result = await team.run(task=step_message)

            step_response = ""
            if hasattr(result, "messages") and result.messages:
                last_msg = result.messages[-1]
                step_response = getattr(last_msg, "content", str(last_msg))

            # Emit step result
            event = StreamEvent(
                event_type=StreamEventType.MESSAGE,
                content=step_response,
                source=agent.name,
                metadata={
                    "step_number": step_idx + 1,
                    "step_name": step_name,
                    "description": description,
                },
            )
            await stream_handler.emit(event)
            yield event

            step_result = {
                "step_number": step_idx + 1,
                "step_name": step_name,
                "agent": agent.name,
                "description": description,
                "response": step_response,
            }
            self.step_results.append(step_result)

            cumulative_context += f"\n{step_name}: {step_response[:300]}...\n"

    def _generate_summary(self) -> str:
        """Generate workflow summary"""
        summary_parts = ["Workflow Summary\n" + "=" * 50]

        for result in self.step_results:
            summary_parts.append(
                f"\n{result['step_number']}. {result['step_name']} ({result['agent']})"
            )
            if result["description"]:
                summary_parts.append(f"   Objective: {result['description']}")
            summary_parts.append(f"   Result: {result['response']}\n")

        return "\n".join(summary_parts)


class HierarchicalOrchestrator:
    """
    Hierarchical orchestrator - coordinator manages specialists.

    Uses SelectorGroupChat where the coordinator (first agent) manages
    specialist agents dynamically.
    """

    def __init__(
        self,
        coordinator: AssistantAgent,
        coordinator_model_client: Any,
        specialists: List[AssistantAgent],
        specialist_model_clients: List[Any],
        max_rounds: int = 20,
    ):
        """
        Initialize hierarchical orchestrator.

        Args:
            coordinator: Coordinator/manager agent
            coordinator_model_client: Model client for coordinator
            specialists: List of specialist agents
            specialist_model_clients: List of model clients for specialists
            max_rounds: Maximum conversation rounds
        """
        require_autogen()
        self.coordinator = coordinator
        self.coordinator_model_client = coordinator_model_client
        self.specialists = specialists
        self.specialist_model_clients = specialist_model_clients
        self.max_rounds = max_rounds
        self.all_agents = [coordinator] + specialists

    async def run(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run hierarchical orchestration.

        Args:
            user_input: Initial context
            context: Optional additional context

        Returns:
            Dict with results
        """
        logger.info("Starting hierarchical orchestration")
        logger.info(f"Coordinator: {self.coordinator.name}")
        logger.info(f"Specialists: {[a.name for a in self.specialists]}")

        # Build initial message for coordinator
        initial_message = f"""
=== TECHNICAL INTERVIEW COORDINATION ===

CANDIDATE PROFILE:
{user_input}

AVAILABLE SPECIALISTS:
{", ".join([a.name for a in self.specialists])}

YOUR ROLE:
1. Understand candidate background
2. Delegate to specialists as needed
3. Synthesize all feedback
4. Provide final recommendation

Please begin the interview:
"""

        # Create SelectorGroupChat with all agents
        # The coordinator's model will select next speaker
        termination = MaxMessageTermination(max_messages=self.max_rounds * 2)
        team = SelectorGroupChat(
            participants=self.all_agents,
            model_client=self.coordinator_model_client,
            termination_condition=termination,
        )

        # Run the team
        result = await team.run(task=initial_message)

        # Extract messages
        messages = []
        if hasattr(result, "messages"):
            messages = result.messages

        # Get coordinator's final assessment (last message from coordinator)
        final_assessment = ""
        for msg in reversed(messages):
            source = getattr(msg, "source", "")
            if source == self.coordinator.name:
                final_assessment = getattr(msg, "content", str(msg))
                break

        if not final_assessment and messages:
            final_assessment = getattr(messages[-1], "content", "No assessment generated")

        # Get specialists used
        specialists_used = list(
            set(
                [
                    getattr(msg, "source", "")
                    for msg in messages
                    if getattr(msg, "source", "") != self.coordinator.name
                ]
            )
        )

        return {
            "final_response": final_assessment,
            "conversation_history": [self._message_to_dict(msg) for msg in messages],
            "coordinator": self.coordinator.name,
            "specialists_used": specialists_used,
            "num_rounds": len(messages),
        }

    async def run_stream(
        self,
        user_input: str,
        stream_handler: "StreamHandler",
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator["StreamEvent", None]:
        """
        Run hierarchical orchestration with streaming.

        Args:
            user_input: Initial context
            stream_handler: Handler for stream events
            context: Optional additional context

        Yields:
            StreamEvent for each message
        """
        from app.agents.schemas import StreamEvent, StreamEventType

        logger.info("Starting streaming hierarchical orchestration")

        initial_message = f"""
=== TECHNICAL INTERVIEW COORDINATION ===

CANDIDATE PROFILE:
{user_input}

AVAILABLE SPECIALISTS:
{", ".join([a.name for a in self.specialists])}

YOUR ROLE:
1. Understand candidate background
2. Delegate to specialists as needed
3. Synthesize all feedback
4. Provide final recommendation

Please begin the interview:
"""

        termination = MaxMessageTermination(max_messages=self.max_rounds * 2)
        team = SelectorGroupChat(
            participants=self.all_agents,
            model_client=self.coordinator_model_client,
            termination_condition=termination,
        )

        # Use run_stream if available
        if hasattr(team, "run_stream"):
            async for message in team.run_stream(task=initial_message):
                if hasattr(message, "content"):
                    event = StreamEvent(
                        event_type=StreamEventType.MESSAGE,
                        content=getattr(message, "content", str(message)),
                        source=getattr(message, "source", "unknown"),
                        metadata={
                            "is_coordinator": getattr(message, "source", "")
                            == self.coordinator.name
                        },
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
                    metadata={
                        "is_coordinator": getattr(msg, "source", "") == self.coordinator.name
                    },
                )
                await stream_handler.emit(event)
                yield event

    def _message_to_dict(self, message) -> Dict[str, Any]:
        """Convert message to dict"""
        return {
            "source": getattr(message, "source", "unknown"),
            "content": getattr(message, "content", str(message)),
        }
