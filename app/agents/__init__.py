"""
Autogen Agent Service - Isolated, reusable wrapper for Autogen

Ported from ``backend/lib/agent_service`` (legacy v3.1.0). This package is
import-safe without the optional AutoGen dependencies: every AutoGen symbol
is routed through :mod:`app.agents.autogen_compat`, and agentic code paths
raise a clear 503-mapped error when invoked without them. Check
``AUTOGEN_AVAILABLE`` (re-exported here) before invoking orchestration.

This service provides a comprehensive interface for:
- Multiple model providers (OpenAI, Azure, Gemini, Ollama, custom)
- Agent orchestration (Round Robin, Group Chat, Workflow, Hierarchical)
- Human-in-the-loop support with callback-based waiting
- Streaming support for real-time message delivery
- MCP integration for technical documentation
- Token usage tracking and cost estimation

Usage:
    from app.agents import AutogenAgentService, AgentConfig, OrchestrationConfig

    service = AutogenAgentService()

    # Basic orchestration
    config = OrchestrationConfig(
        orchestration_type="hierarchical",
        agents=[coordinator_config, specialist1_config, specialist2_config],
        coordinator_agent_index=0,
        enable_mcp_tools=True
    )
    result = await service.orchestrate(config, user_input="...")

    # With human-in-the-loop
    human_config = AgentConfig(
        name="Human_Expert",
        model_name="",  # Not needed for human actors
        system_message="Domain expert who reviews decisions",
        is_human_actor=True
    )

    # Register callback for human input
    async def on_human_input_needed(request):
        print(f"Human input needed: {request.prompt_for_human}")

    service.human_input_handler.register_callback(on_human_input_needed)

    # Streaming orchestration
    async for event in service.orchestrate_stream(config, user_input="..."):
        print(f"[{event.source}]: {event.content}")
"""

from .autogen_compat import AUTOGEN_AVAILABLE
from .exceptions import (
    AgentFrameworkNotInstalledError,
    AgentServiceException,
    ConfigurationError,
    MCPError,
    ModelProviderNotFoundError,
    OrchestrationError,
    TokenUsageError,
)
from .hitl import HumanActorAgent, HumanApprovalAgent, HumanInputHandler
from .schemas import (
    AgentConfig,
    HumanInputMode,
    HumanInputRequest,
    HumanInputResponse,
    OrchestrationConfig,
    StreamEvent,
    StreamEventType,
    WorkflowStep,
)
from .service import AutogenAgentService
from .streaming import StreamHandler, collect_stream, filter_stream
from .utils.retry import (
    DEFAULT_RETRY_CONFIG,
    RetryConfig,
    is_rate_limit_error,
    retry_with_exponential_backoff,
    with_retry,
)

__version__ = "3.1.0"  # Matches the legacy lib/agent_service version

__all__ = [
    # Availability flag
    "AUTOGEN_AVAILABLE",

    # Main service
    "AutogenAgentService",

    # Configuration schemas
    "AgentConfig",
    "OrchestrationConfig",
    "WorkflowStep",

    # Human-in-the-loop
    "HumanInputMode",
    "HumanInputRequest",
    "HumanInputResponse",
    "HumanInputHandler",
    "HumanActorAgent",
    "HumanApprovalAgent",

    # Streaming
    "StreamEvent",
    "StreamEventType",
    "StreamHandler",
    "collect_stream",
    "filter_stream",

    # Retry utilities
    "retry_with_exponential_backoff",
    "with_retry",
    "is_rate_limit_error",
    "RetryConfig",
    "DEFAULT_RETRY_CONFIG",

    # Exceptions
    "AgentServiceException",
    "AgentFrameworkNotInstalledError",
    "ModelProviderNotFoundError",
    "ConfigurationError",
    "OrchestrationError",
    "MCPError",
    "TokenUsageError",
]
