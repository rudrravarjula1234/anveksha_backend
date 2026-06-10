"""Ollama provider using autogen-ext 0.7.5.

Ported from ``backend/lib/agent_service/providers/ollama_provider.py``;
AutoGen imports go through :mod:`app.agents.autogen_compat`. The Ollama
client lives in a separate autogen-ext extra, so it has its own guard.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.agents.autogen_compat import (
    AssistantAgent,
    OllamaChatCompletionClient,
    require_autogen,
    require_ollama,
)

logger = logging.getLogger(__name__)


class OllamaProvider:
    """
    Ollama provider for local models using autogen-ext 0.7.5 API.

    Supports local models like:
    - Llama2
    - Mistral
    - CodeLlama
    - etc.
    """

    def __init__(
        self,
        model_config: Dict[str, Any],
        api_key: Optional[str] = None,  # Not needed for Ollama
        endpoint: Optional[str] = "http://localhost:11434",
    ):
        """
        Initialize Ollama provider.

        Args:
            model_config: Model configuration dict
            api_key: Not used (Ollama doesn't need API key)
            endpoint: Ollama server endpoint (default: http://localhost:11434)
        """
        require_autogen()
        require_ollama()
        self.model_name = model_config.get("model_name")
        self.model_config = model_config
        self.endpoint = endpoint or "http://localhost:11434"

        # Create model client
        self.model_client = self._create_model_client()

    def _create_model_client(self):
        """Create Ollama model client"""
        # Base parameters
        client_params = {
            "model": self.model_name,
            "base_url": self.endpoint,
        }

        # Add LLM parameters from config
        if "temperature" in self.model_config:
            client_params["temperature"] = self.model_config["temperature"]
        if "max_tokens" in self.model_config:
            client_params["max_tokens"] = self.model_config["max_tokens"]
        if "top_p" in self.model_config:
            client_params["top_p"] = self.model_config["top_p"]
        if "frequency_penalty" in self.model_config:
            client_params["frequency_penalty"] = self.model_config["frequency_penalty"]
        if "presence_penalty" in self.model_config:
            client_params["presence_penalty"] = self.model_config["presence_penalty"]

        # Add any provider-specific config
        if "provider_config" in self.model_config:
            for key, value in self.model_config["provider_config"].items():
                if key not in client_params:
                    client_params[key] = value

        return OllamaChatCompletionClient(**client_params)

    async def create_agent(
        self,
        name: str,
        system_message: str,
        **kwargs,
    ) -> AssistantAgent:
        """
        Create an Autogen AssistantAgent with Ollama model.

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

        return agent

    async def direct_call(
        self,
        user_input: str,
        system_message: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Make a direct call to Ollama model.

        Args:
            user_input: User message
            system_message: Optional system message
            **kwargs: Additional parameters

        Returns:
            Model response text
        """
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": user_input})

        # Call model
        response = await self.model_client.create(messages=messages)

        # Extract content
        if response.content:
            return response.content
        elif hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content
        else:
            return str(response)

    async def check_model_available(self) -> bool:
        """
        Check if the Ollama model is available.

        Returns:
            True if model is available, False otherwise
        """
        try:
            await self.direct_call("test", system_message="respond with 'ok'")
            return True
        except Exception as e:
            logger.error(f"Ollama model {self.model_name} not available: {e}")
            return False
