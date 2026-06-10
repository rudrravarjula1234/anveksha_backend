"""Provider factory for autogen 0.7.5.

Ported from ``backend/lib/agent_service/providers/factory.py``.

Port notes:
- ``custom`` (new AdminModel provider "Custom") routes to ``OpenAIProvider``
  with the configured endpoint — custom deployments are assumed to expose an
  OpenAI-compatible API.
- ``anthropic`` / ``bedrock`` map keys exist in the new ``ai_models`` shape
  but the legacy framework never implemented providers for them; they raise
  ``ModelProviderNotFoundError`` exactly like any unsupported provider.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.agents.exceptions import ModelProviderNotFoundError

from .azure_provider import AzureProvider
from .base import BaseModelProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider


class ModelProviderFactory:
    """
    Factory for creating model providers using autogen 0.7.5 API.

    Supports:
    - OpenAI
    - Azure OpenAI
    - Ollama (local models)
    - Google Gemini
    - Custom (OpenAI-compatible endpoints)
    """

    @staticmethod
    def create(
        model_config: Dict[str, Any],
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> BaseModelProvider:
        """
        Create a model provider based on configuration.

        Args:
            model_config: Model configuration dict
            api_key: API key (if required)
            endpoint: Custom endpoint (if applicable)

        Returns:
            Provider instance

        Raises:
            ModelProviderNotFoundError: If provider not supported
        """
        provider_name = model_config.get("model_provider", "").lower()

        # Fall back to the endpoint stored on the model config when the
        # credential record has none (new ai_models docs carry an endpoint).
        endpoint = endpoint or model_config.get("model_endpoint")

        if provider_name == "openai":
            return OpenAIProvider(
                model_config=model_config,
                api_key=api_key,
                endpoint=endpoint,
            )

        elif provider_name in ["azure", "azure_openai"]:
            if not endpoint:
                raise ValueError("Azure OpenAI requires an endpoint")
            return AzureProvider(
                model_config=model_config,
                api_key=api_key,
                endpoint=endpoint,
            )

        elif provider_name == "ollama":
            return OllamaProvider(
                model_config=model_config,
                api_key=api_key,
                endpoint=endpoint or "http://localhost:11434",
            )

        elif provider_name in ["gemini", "google"]:
            return GeminiProvider(
                model_config=model_config,
                api_key=api_key,
                endpoint=endpoint,
            )

        elif provider_name == "custom":
            # OpenAI-compatible custom deployment.
            return OpenAIProvider(
                model_config=model_config,
                api_key=api_key,
                endpoint=endpoint,
            )

        else:
            raise ModelProviderNotFoundError(
                f"Provider '{provider_name}' not supported. "
                f"Supported: openai, azure, ollama, gemini/google, custom"
            )

    @staticmethod
    def auto_detect_provider(model_name: str) -> str:
        """
        Auto-detect provider based on model name.

        Args:
            model_name: Model name

        Returns:
            Provider name
        """
        model_name_lower = model_name.lower()

        # OpenAI models
        if any(x in model_name_lower for x in ["gpt-", "gpt4", "gpt3"]):
            return "openai"

        # Ollama/local models
        if any(x in model_name_lower for x in ["llama", "mistral", "codellama", "mixtral", "phi"]):
            return "ollama"

        # Gemini models
        if any(x in model_name_lower for x in ["gemini", "bard"]):
            return "gemini"

        # Default to openai
        return "openai"
