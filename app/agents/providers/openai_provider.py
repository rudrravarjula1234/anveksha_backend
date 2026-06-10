"""OpenAI provider using autogen-ext 0.7.5.

Ported from ``backend/lib/agent_service/providers/openai_provider.py``;
AutoGen imports are routed through :mod:`app.agents.autogen_compat` and the
constructor raises a clear error when the optional packages are missing.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, Optional

from app.agents.autogen_compat import (
    AssistantAgent,
    AzureOpenAIChatCompletionClient,
    OpenAIChatCompletionClient,
    require_autogen,
)

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """
    OpenAI provider using autogen-ext 0.7.5 API.

    Supports:
    - Standard OpenAI models (GPT-4, GPT-3.5)
    - Azure OpenAI
    - Custom endpoints
    """

    def __init__(
        self,
        model_config: Dict[str, Any],
        api_key: str,
        endpoint: Optional[str] = None,
    ):
        """
        Initialize OpenAI provider.

        Args:
            model_config: Model configuration dict
            api_key: OpenAI API key
            endpoint: Optional custom endpoint (for Azure)
        """
        require_autogen()
        self.model_name = model_config.get("model_name")
        self.model_config = model_config
        self.api_key = api_key
        self.endpoint = endpoint

        # Determine if Azure or standard OpenAI
        self.is_azure = endpoint and "azure" in endpoint.lower()

        # Create model client
        self.model_client = self._create_model_client()

    def _create_model_client(self):
        """Create OpenAI or Azure OpenAI model client"""
        # Base parameters
        client_params = {
            "model": self.model_name,
            "api_key": self.api_key,
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

        if self.is_azure:
            # Azure OpenAI specific parameters
            client_params["azure_endpoint"] = self.endpoint
            client_params["api_version"] = self.model_config.get("provider_config", {}).get(
                "api_version", "2024-02-01"
            )
            if "azure_deployment" in self.model_config.get("provider_config", {}):
                client_params["azure_deployment"] = self.model_config["provider_config"][
                    "azure_deployment"
                ]
            return AzureOpenAIChatCompletionClient(**client_params)
        else:
            # Standard OpenAI
            return OpenAIChatCompletionClient(**client_params)

    async def create_agent(
        self,
        name: str,
        system_message: str,
        **kwargs,
    ) -> AssistantAgent:
        """
        Create an Autogen AssistantAgent with this model.

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
        Make a direct call to the model without creating an agent.

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

    async def direct_call_stream(
        self,
        user_input: str,
        system_message: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Make a streaming direct call to the OpenAI model.

        Args:
            user_input: User message
            system_message: Optional system message
            **kwargs: Additional parameters

        Yields:
            Token strings as they are generated
        """
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": user_input})

        # Stream from model using create_stream
        try:
            async for chunk in self.model_client.create_stream(messages=messages):
                # Extract content from chunk
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
                elif hasattr(chunk, "delta") and hasattr(chunk.delta, "content"):
                    if chunk.delta.content:
                        yield chunk.delta.content
                elif hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        yield delta.content
        except AttributeError:
            # Fallback if streaming not supported
            logger.warning("Streaming not supported, falling back to non-streaming")
            response = await self.direct_call(user_input, system_message, **kwargs)
            yield response
