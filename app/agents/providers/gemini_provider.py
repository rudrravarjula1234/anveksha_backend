"""Google Gemini provider using autogen-ext 0.7.5.

Ported from ``backend/lib/agent_service/providers/gemini_provider.py``;
AutoGen imports go through :mod:`app.agents.autogen_compat`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.agents.autogen_compat import (
    AssistantAgent,
    ModelFamily,
    OpenAIChatCompletionClient,
    SystemMessage,
    UserMessage,
    require_autogen,
)

logger = logging.getLogger(__name__)


class GeminiProvider:
    """
    Google Gemini provider using autogen-ext 0.7.5 API.

    Supports:
    - Gemini 1.5 Pro
    - Gemini 1.5 Flash
    - Gemini 2.0 Flash
    - Gemini Pro (legacy)
    - Gemini Pro Vision (legacy)

    Uses OpenAI-compatible client with built-in Gemini support.
    The OpenAIChatCompletionClient automatically handles Gemini models
    by detecting the model name prefix and using the correct endpoint.
    """

    def __init__(
        self,
        model_config: Dict[str, Any],
        api_key: str,
        endpoint: Optional[str] = None,
    ):
        """
        Initialize Gemini provider.

        Args:
            model_config: Model configuration dict
            api_key: Google AI Studio API key (or GEMINI_API_KEY env var)
            endpoint: Optional custom endpoint (auto-detected for Gemini models)
        """
        require_autogen()
        self.model_name = model_config.get("model_name", "gemini-1.5-flash")
        self.model_config = model_config
        self.api_key = api_key
        self.endpoint = endpoint

        # Create model client
        self.model_client = self._create_model_client()

    def _create_model_client(self):
        """
        Create Gemini model client using OpenAI-compatible interface.

        The OpenAIChatCompletionClient has built-in support for Gemini models.
        When model name starts with 'gemini-', it automatically:
        1. Uses the correct Gemini OpenAI-compatible endpoint
        2. Checks for GEMINI_API_KEY env var if api_key not provided
        3. Applies appropriate model capabilities
        """
        # Determine model family and capabilities based on model name
        model_info = self._get_model_info()

        # Extract LLM parameters from model config
        client_params = {
            "model": self.model_name,
            "api_key": self.api_key,
            "model_info": model_info,
        }

        # Add endpoint if provided
        if self.endpoint:
            client_params["base_url"] = self.endpoint

        # Add LLM parameters if present in config
        # NOTE: Gemini API only supports temperature, max_tokens, and top_p
        # It does NOT support frequency_penalty or presence_penalty
        if "temperature" in self.model_config:
            client_params["temperature"] = self.model_config["temperature"]
        if "max_tokens" in self.model_config:
            client_params["max_tokens"] = self.model_config["max_tokens"]
        if "top_p" in self.model_config:
            client_params["top_p"] = self.model_config["top_p"]

        # Add any provider-specific config
        if "provider_config" in self.model_config:
            for key, value in self.model_config["provider_config"].items():
                if key not in client_params:
                    client_params[key] = value

        return OpenAIChatCompletionClient(**client_params)

    def _get_model_info(self) -> Dict[str, Any]:
        """Get model capabilities based on model name"""
        model_lower = self.model_name.lower()

        # Determine if model supports vision
        vision = "vision" in model_lower or "2.0" in model_lower or "1.5" in model_lower

        # Determine model family
        if "gemini-2.0-flash" in model_lower:
            family = ModelFamily.GEMINI_2_0_FLASH
        elif "gemini-1.5-flash" in model_lower:
            family = ModelFamily.GEMINI_1_5_FLASH
        elif "1.5-pro" in model_lower:
            family = ModelFamily.GEMINI_1_5_PRO
        else:
            family = ModelFamily.UNKNOWN

        return {
            "vision": vision,
            "function_calling": True,  # All Gemini models support function calling
            "json_output": True,
            "family": family,
            "structured_output": True,
        }

    async def create_agent(
        self,
        name: str,
        system_message: str,
        **kwargs,
    ) -> AssistantAgent:
        """
        Create an Autogen AssistantAgent with Gemini model.

        Args:
            name: Agent name
            system_message: System message/prompt
            **kwargs: Additional agent configuration

        Returns:
            AssistantAgent instance
        """
        agent = AssistantAgent(
            name=name,
            model_client=self.model_client,
            system_message=system_message,
            **kwargs,
        )

        logger.info(f"Created Gemini agent '{name}' with model {self.model_name}")
        return agent

    async def direct_call(
        self,
        user_input: str,
        system_message: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Make a direct call to Gemini without creating an agent.

        Args:
            user_input: User message
            system_message: Optional system message
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Model response text
        """
        # Build messages for Gemini
        messages = []

        if system_message:
            messages.append(SystemMessage(content=system_message, source="system"))

        messages.append(UserMessage(content=user_input, source="user"))

        # Call model
        try:
            response = await self.model_client.create(messages=messages, **kwargs)

            # Extract content from response
            return response.content

        except Exception as e:
            logger.error(f"Gemini direct call failed: {str(e)}")
            raise

    def get_supported_models(self) -> list[str]:
        """
        Return list of supported Gemini models.

        Returns:
            List of model names
        """
        return [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-pro",  # Legacy
            "gemini-pro-vision",  # Legacy
        ]

    @property
    def supports_vision(self) -> bool:
        """Check if current model supports vision/image input"""
        model_lower = self.model_name.lower()
        return "vision" in model_lower or "1.5" in model_lower or "2.0" in model_lower

    @property
    def supports_function_calling(self) -> bool:
        """Check if current model supports function calling"""
        return True  # All Gemini models support function calling

    @property
    def supports_structured_output(self) -> bool:
        """Check if current model supports structured output"""
        return True  # All recent Gemini models support structured output
