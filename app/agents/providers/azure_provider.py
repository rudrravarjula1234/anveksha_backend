"""Azure OpenAI provider using autogen-ext 0.7.5.

Ported from ``backend/lib/agent_service/providers/azure_provider.py``;
AutoGen imports go through :mod:`app.agents.autogen_compat`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.agents.autogen_compat import (
    AssistantAgent,
    AzureOpenAIChatCompletionClient,
    require_autogen,
)

logger = logging.getLogger(__name__)


class AzureProvider:
    """
    Azure OpenAI provider using autogen-ext 0.7.5 API.

    Supports:
    - Azure OpenAI models (GPT-4, GPT-3.5, etc.)
    - Custom Azure deployments
    - Identity-based authentication (optional)
    """

    def __init__(
        self,
        model_config: Dict[str, Any],
        api_key: str,
        endpoint: str,
    ):
        """
        Initialize Azure OpenAI provider.

        Args:
            model_config: Model configuration dict
            api_key: Azure OpenAI API key
            endpoint: Azure OpenAI endpoint (e.g., https://{resource}.openai.azure.com/)
        """
        require_autogen()
        self.model_name = model_config.get("model_name")
        self.model_config = model_config
        self.api_key = api_key
        self.endpoint = endpoint

        # Azure-specific: get deployment name (often same as model name)
        self.deployment_name = model_config.get("provider_config", {}).get(
            "azure_deployment", self.model_name
        )

        # Create model client
        self.model_client = self._create_model_client()

    def _create_model_client(self):
        """Create Azure OpenAI model client"""
        # Base parameters
        client_params = {
            "model": self.deployment_name,  # Azure uses deployment name
            "api_key": self.api_key,
            "azure_endpoint": self.endpoint,
            "api_version": self.model_config.get("provider_config", {}).get(
                "api_version", "2024-02-01"
            ),
        }

        # Add azure_deployment if different from model
        if self.deployment_name != self.model_name:
            client_params["azure_deployment"] = self.deployment_name

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

        # Add any additional provider-specific config
        if "provider_config" in self.model_config:
            for key, value in self.model_config["provider_config"].items():
                if key not in client_params and key not in ["azure_deployment", "api_version"]:
                    client_params[key] = value

        return AzureOpenAIChatCompletionClient(**client_params)

    async def create_agent(
        self,
        name: str,
        system_message: str,
        **kwargs,
    ) -> AssistantAgent:
        """
        Create an Autogen AssistantAgent with Azure OpenAI model.

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

        logger.info(f"Created Azure OpenAI agent '{name}' with deployment {self.deployment_name}")
        return agent

    async def direct_call(
        self,
        user_input: str,
        system_message: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Make a direct call to Azure OpenAI without creating an agent.

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
        response = await self.model_client.create(messages=messages, **kwargs)

        # Extract content
        if response.content:
            return response.content
        elif hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content
        else:
            return str(response)
