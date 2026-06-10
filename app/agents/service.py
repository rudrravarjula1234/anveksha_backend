"""Main Autogen Agent Service - autogen 0.7.5.

Ported from ``backend/lib/agent_service/service.py``. Differences from the
legacy version:

- AutoGen access is guarded via :mod:`app.agents.autogen_compat` (the import
  of this module never pulls AutoGen in; orchestration raises a clear error
  when the optional packages are missing).
- The optional PII sanitizer is looked up at ``app.core.pii.llm_sanitizer``
  (the new backend has no such module today, so the lazy import quietly
  returns ``None`` — identical behaviour to a legacy deployment without the
  PII package).
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from .config import AgentServiceConfig
from .exceptions import (
    ConfigurationError,
    ModelConfigNotFoundError,
    OrchestrationError,
)
from .hitl.handler import HumanInputHandler
from .hitl.human_agent import HumanActorAgent
from .mcp.mcp_manager import MCPManager
from .orchestrators import (
    GroupChatOrchestrator,
    HierarchicalOrchestrator,
    RoundRobinOrchestrator,
    WorkflowOrchestrator,
)
from .providers.factory import ModelProviderFactory
from .schemas import (
    AgentConfig,
    OrchestrationConfig,
    StreamEvent,
    StreamEventType,
)
from .streaming.stream_handler import StreamHandler
from .token_usage.cost_calculator import CostCalculator
from .token_usage.token_counter import TokenCounter
from .token_usage.usage_logger import UsageLogger
from .utils.retry import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


# Lazy import to avoid circular dependency — PII module is optional
def _get_sanitizer():
    try:
        from app.core.pii.llm_sanitizer import LLMSanitizer

        return LLMSanitizer()
    except ImportError:
        return None


class AutogenAgentService:
    """
    Main service class for Autogen operations - autogen 0.7.5 API.

    Supports config-based orchestration where you pass agent configurations
    directly instead of fetching from database.

    Features:
    - Multi-provider support (OpenAI, Azure, Gemini, Ollama)
    - Multiple orchestration patterns (round-robin, group chat, workflow, hierarchical)
    - Human-in-the-loop support with callback-based waiting
    - Streaming support for token and message-level events
    - MCP integration for tool calling
    - Token usage tracking and cost estimation
    """

    def __init__(
        self,
        config: Optional[AgentServiceConfig] = None,
        human_input_handler: Optional[HumanInputHandler] = None,
    ):
        """
        Initialize the Autogen Agent Service.

        Args:
            config: Service configuration
            human_input_handler: Optional custom HITL handler (creates default if None)
        """
        self.config = config or AgentServiceConfig()
        self.mcp_manager = MCPManager()
        self._human_input_handler = human_input_handler or HumanInputHandler()
        self._stream_handler: Optional[StreamHandler] = None
        logger.info("Autogen Agent Service initialized (autogen 0.7.5)")

    @property
    def human_input_handler(self) -> HumanInputHandler:
        """Get the human input handler for registering callbacks"""
        return self._human_input_handler

    async def direct_call(
        self,
        model_name: str,
        user_input: str,
        system_message: Optional[str] = None,
        track_usage: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make a direct call to an LLM without using agents.

        Args:
            model_name: Model name to use
            user_input: User message
            system_message: Optional system message
            track_usage: Whether to track token usage

        Returns:
            Dict with response and optional token usage
        """
        start_time = time.time()

        # Get model config
        model_config = self.config.model_cache.get(model_name)
        if not model_config:
            raise ModelConfigNotFoundError(f"Model configuration not found: {model_name}")

        # Get credentials
        provider_name = model_config.get("model_provider")
        api_key = self.config.credential_cache.get_api_key(provider_name)
        endpoint = self.config.credential_cache.get_endpoint(provider_name)

        # Create provider
        provider = ModelProviderFactory.create(
            model_config=model_config,
            api_key=api_key,
            endpoint=endpoint,
        )

        # PII sanitization — strip PII before sending to LLM
        sanitizer = _get_sanitizer()
        sanitized_input = user_input
        sanitized_system = system_message
        if sanitizer:
            sanitized_input = sanitizer.sanitize(user_input)
            if system_message:
                sanitized_system = sanitizer.sanitize(system_message)
            pii_stats = sanitizer.get_stats()
            if any(v > 0 for v in pii_stats.values()):
                logger.info("PII sanitized before LLM call: %s", pii_stats)

        # Make the call
        response = await provider.direct_call(sanitized_input, sanitized_system, **kwargs)

        # De-sanitize response if needed
        if sanitizer and isinstance(response, str):
            response = sanitizer.desanitize(response)

        duration_ms = int((time.time() - start_time) * 1000)

        result = {
            "response": response,
            "model_name": model_name,
            "duration_ms": duration_ms,
        }

        # Track token usage if enabled
        if track_usage and self.config.enable_token_tracking:
            usage_info = await self._track_usage(
                agent_ids=[],
                model_name=model_name,
                model_config=model_config,
                orchestration_type="direct",
                user_input=user_input,
                response=response,
                duration_ms=duration_ms,
            )
            result["token_usage"] = usage_info

        return result

    async def direct_call_stream(
        self,
        model_name: str,
        user_input: str,
        system_message: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Make a streaming direct call to an LLM.

        Yields tokens as they are generated for real-time display.

        Args:
            model_name: Model name to use
            user_input: User message
            system_message: Optional system message

        Yields:
            Token strings as they are generated
        """
        # Get model config
        model_config = self.config.model_cache.get(model_name)
        if not model_config:
            raise ModelConfigNotFoundError(f"Model configuration not found: {model_name}")

        # Get credentials
        provider_name = model_config.get("model_provider")
        api_key = self.config.credential_cache.get_api_key(provider_name)
        endpoint = self.config.credential_cache.get_endpoint(provider_name)

        # Create provider
        provider = ModelProviderFactory.create(
            model_config=model_config,
            api_key=api_key,
            endpoint=endpoint,
        )

        # Stream from provider
        async for token in provider.direct_call_stream(user_input, system_message, **kwargs):
            yield token

    async def orchestrate(
        self,
        config: OrchestrationConfig,
        user_input: str,
        track_usage: bool = True,
    ) -> Dict[str, Any]:
        """
        Run orchestration with the specified configuration.

        Args:
            config: OrchestrationConfig with agents and settings
            user_input: User input/interview context
            track_usage: Whether to track token usage

        Returns:
            Dict with orchestration results and token usage
        """
        start_time = time.time()

        logger.info(f"Starting orchestration: {config.orchestration_type}")
        logger.info(f"Agents: {[a.name for a in config.agents]}")

        # PII sanitization on orchestration input
        sanitizer = _get_sanitizer()
        if sanitizer:
            user_input = sanitizer.sanitize(user_input)
            pii_stats = sanitizer.get_stats()
            if any(v > 0 for v in pii_stats.values()):
                logger.info("PII sanitized before orchestration: %s", pii_stats)

        # Create Autogen agents from configs
        autogen_agents = await self._create_agents_from_configs(config.agents)

        # MCP tools are registered within agent creation if enabled
        # (handled by model clients in autogen 0.7.5)

        # Select and run orchestrator with retry logic for rate limiting
        if config.retry_enabled:
            result = await retry_with_exponential_backoff(
                self._run_orchestrator,
                orchestration_type=config.orchestration_type,
                agents=autogen_agents,
                user_input=user_input,
                config=config,
                max_retries=config.retry_max_attempts,
                initial_delay=config.retry_initial_delay,
                max_delay=config.retry_max_delay,
            )
        else:
            result = await self._run_orchestrator(
                orchestration_type=config.orchestration_type,
                agents=autogen_agents,
                user_input=user_input,
                config=config,
            )

        duration_ms = int((time.time() - start_time) * 1000)
        result["duration_ms"] = duration_ms
        result["orchestration_type"] = config.orchestration_type

        # Track token usage
        if track_usage and self.config.enable_token_tracking:
            model_name = config.agents[0].model_name
            model_config = self.config.model_cache.get(model_name)

            if model_config:
                usage_info = await self._track_usage(
                    agent_ids=[a.name for a in config.agents],
                    model_name=model_name,
                    model_config=model_config,
                    orchestration_type=config.orchestration_type,
                    user_input=user_input,
                    response=result.get("final_response", ""),
                    duration_ms=duration_ms,
                    conversation_history=result.get("conversation_history", []),
                )
                result["token_usage"] = usage_info

        return result

    async def orchestrate_stream(
        self,
        config: OrchestrationConfig,
        user_input: str,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Run orchestration with streaming events.

        Yields StreamEvent objects for real-time message display.
        Supports human-in-the-loop when agents have is_human_actor=True.

        Args:
            config: OrchestrationConfig with agents and settings
            user_input: User input/interview context

        Yields:
            StreamEvent objects as messages are produced
        """
        logger.info(f"Starting streaming orchestration: {config.orchestration_type}")

        # Create stream handler for this orchestration
        stream_handler = StreamHandler()
        self._stream_handler = stream_handler

        # Emit start event
        await stream_handler.emit_status(
            "started",
            metadata={
                "orchestration_type": config.orchestration_type,
                "agent_count": len(config.agents),
            },
        )

        try:
            # Create Autogen agents from configs (includes human actors)
            autogen_agents = await self._create_agents_from_configs(
                config.agents,
                stream_handler=stream_handler,
            )

            # Run streaming orchestrator
            async for event in self._run_orchestrator_stream(
                orchestration_type=config.orchestration_type,
                agents=autogen_agents,
                user_input=user_input,
                config=config,
                stream_handler=stream_handler,
            ):
                yield event

            # Emit completion event
            await stream_handler.emit_status("completed")
            yield StreamEvent(
                event_type=StreamEventType.STATUS,
                content="completed",
            )

        except Exception as e:
            logger.error(f"Streaming orchestration error: {e}")
            await stream_handler.emit_error(str(e))
            yield StreamEvent(
                event_type=StreamEventType.ERROR,
                content=str(e),
            )
        finally:
            self._stream_handler = None

    async def _create_agents_from_configs(
        self,
        agent_configs: List[AgentConfig],
        stream_handler: Optional[StreamHandler] = None,
    ) -> List:
        """
        Create Autogen agents from AgentConfig objects.

        Handles both AI agents and human actor agents.

        Args:
            agent_configs: List of agent configurations
            stream_handler: Optional stream handler for streaming orchestrations

        Returns:
            List of dicts with agent, model_client, and provider
        """
        autogen_agents = []

        for agent_config in agent_configs:
            # Check if this is a human actor agent
            if agent_config.is_human_actor:
                # Create human actor agent
                human_agent = HumanActorAgent(
                    name=agent_config.name,
                    handler=self._human_input_handler,
                    description=agent_config.system_message,
                    input_mode=agent_config.human_input_mode,
                    timeout_seconds=300,
                )

                autogen_agents.append(
                    {
                        "agent": human_agent,
                        "model_client": None,  # Human agents don't use model clients
                        "provider": None,
                        "is_human": True,
                    }
                )

                logger.info(f"Created Human Actor Agent: {agent_config.name}")
                continue

            # AI Agent - Get model config
            model_config = self.config.model_cache.get(agent_config.model_name)
            if not model_config:
                raise ModelConfigNotFoundError(
                    f"Model config not found: {agent_config.model_name}"
                )

            # Get credentials
            provider_name = model_config.get("model_provider")
            api_key = self.config.credential_cache.get_api_key(provider_name)
            endpoint = self.config.credential_cache.get_endpoint(provider_name)

            # Create provider
            provider = ModelProviderFactory.create(
                model_config=model_config,
                api_key=api_key,
                endpoint=endpoint,
            )

            # Create agent
            autogen_agent = await provider.create_agent(
                name=agent_config.name,
                system_message=agent_config.system_message,
            )

            # Store agent with its model client and provider
            autogen_agents.append(
                {
                    "agent": autogen_agent,
                    "model_client": provider.model_client,
                    "provider": provider,
                    "is_human": False,
                }
            )

        logger.info(
            f"Created {len(autogen_agents)} agents "
            f"({sum(1 for a in autogen_agents if a.get('is_human'))} human actors)"
        )
        return autogen_agents

    async def _run_orchestrator(
        self,
        orchestration_type: str,
        agents: List,
        user_input: str,
        config: OrchestrationConfig,
    ) -> Dict[str, Any]:
        """Run the appropriate orchestrator based on type"""

        # Extract agent objects and model clients
        agent_list = [a["agent"] for a in agents]
        model_clients = [a["model_client"] for a in agents]

        if orchestration_type == "group_chat":
            orchestrator = GroupChatOrchestrator(
                agents=agent_list,
                model_clients=model_clients,
                max_rounds=config.max_rounds,
            )
            orchestrator.setup_group_chat(config.speaker_selection_method)
            return await orchestrator.run(user_input)

        elif orchestration_type == "round_robin":
            orchestrator = RoundRobinOrchestrator(
                agents=agent_list,
                model_clients=model_clients,
                max_rounds=config.max_rounds,
            )
            return await orchestrator.run(user_input)

        elif orchestration_type == "workflow":
            if not config.workflow_steps:
                raise ConfigurationError("workflow_steps required for workflow orchestration")

            orchestrator = WorkflowOrchestrator(
                agents=agent_list,
                model_clients=model_clients,
                workflow_steps=config.workflow_steps,
            )
            return await orchestrator.run(user_input)

        elif orchestration_type == "hierarchical":
            if config.coordinator_agent_index is None:
                raise ConfigurationError(
                    "coordinator_agent_index required for hierarchical orchestration"
                )

            coordinator_idx = config.coordinator_agent_index
            coordinator = agents[coordinator_idx]["agent"]
            coordinator_model_client = agents[coordinator_idx]["model_client"]

            specialists = [agents[i]["agent"] for i in range(len(agents)) if i != coordinator_idx]
            specialist_model_clients = [
                agents[i]["model_client"] for i in range(len(agents)) if i != coordinator_idx
            ]

            orchestrator = HierarchicalOrchestrator(
                coordinator=coordinator,
                coordinator_model_client=coordinator_model_client,
                specialists=specialists,
                specialist_model_clients=specialist_model_clients,
                max_rounds=config.max_rounds,
            )
            return await orchestrator.run(user_input)

        else:
            raise OrchestrationError(f"Unknown orchestration type: {orchestration_type}")

    async def _run_orchestrator_stream(
        self,
        orchestration_type: str,
        agents: List,
        user_input: str,
        config: OrchestrationConfig,
        stream_handler: StreamHandler,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Run orchestrator with streaming output.

        Yields StreamEvent objects for each message produced.
        """
        # Extract agent objects and model clients (filter None for human agents)
        agent_list = [a["agent"] for a in agents]
        model_clients = [a["model_client"] for a in agents if a["model_client"] is not None]

        # For now, run non-streaming and emit messages as events
        # Full streaming support requires orchestrator updates
        if orchestration_type == "group_chat":
            orchestrator = GroupChatOrchestrator(
                agents=agent_list,
                model_clients=model_clients if model_clients else [None],
                max_rounds=config.max_rounds,
            )
            orchestrator.setup_group_chat(config.speaker_selection_method)

            # Try streaming if available
            if hasattr(orchestrator, "run_stream"):
                async for event in orchestrator.run_stream(user_input, stream_handler):
                    yield event
            else:
                result = await orchestrator.run(user_input)
                for msg in result.get("conversation_history", []):
                    yield StreamEvent(
                        event_type=StreamEventType.MESSAGE,
                        content=msg.get("content", ""),
                        source=msg.get("source", "unknown"),
                    )

        elif orchestration_type == "round_robin":
            orchestrator = RoundRobinOrchestrator(
                agents=agent_list,
                model_clients=model_clients if model_clients else [None],
                max_rounds=config.max_rounds,
            )

            if hasattr(orchestrator, "run_stream"):
                async for event in orchestrator.run_stream(user_input, stream_handler):
                    yield event
            else:
                result = await orchestrator.run(user_input)
                for msg in result.get("conversation_history", []):
                    yield StreamEvent(
                        event_type=StreamEventType.MESSAGE,
                        content=msg.get("content", ""),
                        source=msg.get("source", "unknown"),
                    )

        elif orchestration_type == "workflow":
            if not config.workflow_steps:
                raise ConfigurationError("workflow_steps required for workflow orchestration")

            orchestrator = WorkflowOrchestrator(
                agents=agent_list,
                model_clients=model_clients if model_clients else [None],
                workflow_steps=config.workflow_steps,
            )

            if hasattr(orchestrator, "run_stream"):
                async for event in orchestrator.run_stream(user_input, stream_handler):
                    yield event
            else:
                result = await orchestrator.run(user_input)
                for step_result in result.get("step_results", []):
                    yield StreamEvent(
                        event_type=StreamEventType.MESSAGE,
                        content=step_result.get("response", ""),
                        source=step_result.get("agent", "unknown"),
                        metadata={"step_name": step_result.get("step_name")},
                    )

        elif orchestration_type == "hierarchical":
            if config.coordinator_agent_index is None:
                raise ConfigurationError("coordinator_agent_index required")

            coordinator_idx = config.coordinator_agent_index
            coordinator = agents[coordinator_idx]["agent"]
            coordinator_model_client = agents[coordinator_idx]["model_client"]

            specialists = [agents[i]["agent"] for i in range(len(agents)) if i != coordinator_idx]
            specialist_model_clients = [
                agents[i]["model_client"]
                for i in range(len(agents))
                if i != coordinator_idx and agents[i]["model_client"] is not None
            ]

            orchestrator = HierarchicalOrchestrator(
                coordinator=coordinator,
                coordinator_model_client=coordinator_model_client,
                specialists=specialists,
                specialist_model_clients=(
                    specialist_model_clients if specialist_model_clients else [None]
                ),
                max_rounds=config.max_rounds,
            )

            if hasattr(orchestrator, "run_stream"):
                async for event in orchestrator.run_stream(user_input, stream_handler):
                    yield event
            else:
                result = await orchestrator.run(user_input)
                for msg in result.get("conversation_history", []):
                    yield StreamEvent(
                        event_type=StreamEventType.MESSAGE,
                        content=msg.get("content", ""),
                        source=msg.get("source", "unknown"),
                    )
        else:
            raise OrchestrationError(f"Unknown orchestration type: {orchestration_type}")

    async def _track_usage(
        self,
        agent_ids: List[str],
        model_name: str,
        model_config: Dict[str, Any],
        orchestration_type: str,
        user_input: str,
        response: str,
        duration_ms: int,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Track token usage and calculate costs"""
        provider_name = model_config.get("model_provider")

        # Create token counter
        counter = TokenCounter(model_name, provider_name)

        # Count tokens
        if conversation_history:
            input_tokens = counter.count_messages_tokens(conversation_history)
            output_tokens = counter.count_tokens(response)
        else:
            input_tokens = counter.count_tokens(user_input)
            output_tokens = counter.count_tokens(response)

        # Calculate costs
        pricing = model_config.get("pricing")
        calculator = CostCalculator(pricing)
        cost_breakdown = calculator.calculate_total_cost(input_tokens, output_tokens)

        # Log usage
        request_id = await UsageLogger.log_usage(
            agent_ids=agent_ids,
            model_name=model_name,
            orchestration_type=orchestration_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=cost_breakdown["input_cost"],
            output_cost=cost_breakdown["output_cost"],
            currency=cost_breakdown["currency"],
            duration_ms=duration_ms,
        )

        return {
            "request_id": request_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            **cost_breakdown,
        }

    def is_initialized(self) -> bool:
        """Check if service is properly initialized"""
        return self.config.is_initialized()

    async def shutdown(self):
        """Gracefully shutdown the service"""
        logger.info("Shutting down Autogen Agent Service")
        await self.mcp_manager.disconnect_all()
