"""Central guard for the optional AutoGen dependencies.

Every module in ``app.agents`` that needs an AutoGen symbol imports it from
here instead of from ``autogen_agentchat`` / ``autogen_ext`` / ``autogen_core``
directly. When the optional packages are not installed, the placeholders below
keep the whole package importable — the API boots normally and only the
agentic endpoints fail (with a clear 503) when actually invoked.

Install the full agentic stack with:

    pip install autogen-core==0.7.5 autogen-agentchat==0.7.5 \
        "autogen-ext[openai,anthropic,azure,ollama,mcp]==0.7.5" "tiktoken>=0.5.0"
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── autogen-agentchat / autogen-core (required for any orchestration) ────
try:
    from autogen_agentchat.agents import AssistantAgent, BaseChatAgent
    from autogen_agentchat.base import Response
    from autogen_agentchat.conditions import (
        MaxMessageTermination,
        TextMentionTermination,
    )
    from autogen_agentchat.messages import ChatMessage, TextMessage
    from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
    from autogen_core import CancellationToken
    from autogen_core.models import ModelFamily, SystemMessage, UserMessage

    _AGENTCHAT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on optional install
    _AGENTCHAT_AVAILABLE = False
    AssistantAgent = None  # type: ignore[assignment]
    BaseChatAgent = object  # type: ignore[assignment]  # safe stand-in for subclassing
    Response = None  # type: ignore[assignment]
    MaxMessageTermination = None  # type: ignore[assignment]
    TextMentionTermination = None  # type: ignore[assignment]
    ChatMessage = Any  # type: ignore[assignment]
    TextMessage = None  # type: ignore[assignment]
    RoundRobinGroupChat = None  # type: ignore[assignment]
    SelectorGroupChat = None  # type: ignore[assignment]
    CancellationToken = Any  # type: ignore[assignment]
    ModelFamily = None  # type: ignore[assignment]
    SystemMessage = None  # type: ignore[assignment]
    UserMessage = None  # type: ignore[assignment]

# ── autogen-ext model clients (the OpenAI-compatible client also covers
#    Azure and Gemini in the 0.7.5 API) ───────────────────────────────────
try:
    from autogen_ext.models.openai import (
        AzureOpenAIChatCompletionClient,
        OpenAIChatCompletionClient,
    )

    _OPENAI_EXT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OPENAI_EXT_AVAILABLE = False
    OpenAIChatCompletionClient = None  # type: ignore[assignment]
    AzureOpenAIChatCompletionClient = None  # type: ignore[assignment]

try:
    from autogen_ext.models.ollama import OllamaChatCompletionClient

    _OLLAMA_EXT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OLLAMA_EXT_AVAILABLE = False
    OllamaChatCompletionClient = None  # type: ignore[assignment]

# The feedback pipeline needs agentchat + the OpenAI-compatible ext client
# (used for OpenAI, Azure and Gemini). Ollama support is tracked separately.
AUTOGEN_AVAILABLE: bool = _AGENTCHAT_AVAILABLE and _OPENAI_EXT_AVAILABLE
OLLAMA_AVAILABLE: bool = _OLLAMA_EXT_AVAILABLE

if not AUTOGEN_AVAILABLE:
    logger.info(
        "AutoGen packages not installed — agentic endpoints are disabled. "
        "Install autogen-agentchat / autogen-ext to enable them."
    )


def require_autogen() -> None:
    """Raise a clear error when agentic code paths run without AutoGen.

    The exception type is imported lazily to avoid a circular import.
    """
    if AUTOGEN_AVAILABLE:
        return
    from app.agents.exceptions import AgentFrameworkNotInstalledError

    raise AgentFrameworkNotInstalledError(
        "Agent framework dependencies not installed. Install the optional "
        "agent extras: pip install autogen-core==0.7.5 autogen-agentchat==0.7.5 "
        "'autogen-ext[openai,anthropic,azure,ollama,mcp]==0.7.5'"
    )


def require_ollama() -> None:
    """Raise when the Ollama provider is used without autogen-ext[ollama]."""
    if _OLLAMA_EXT_AVAILABLE:
        return
    from app.agents.exceptions import AgentFrameworkNotInstalledError

    raise AgentFrameworkNotInstalledError(
        "Ollama support requires the optional dependency: "
        "pip install 'autogen-ext[ollama]==0.7.5'"
    )
