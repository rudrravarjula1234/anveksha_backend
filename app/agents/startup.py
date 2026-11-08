"""Startup initialization for Autogen Agent Service.

Ported from ``backend/lib/agent_service/startup.py``. Differences:

- Model configs come from the ``ai_models`` table via
  :mod:`app.agents.model_config_adapter` (legacy: ``services.model_config_service``).
- Credentials come from :mod:`app.agents.credentials` (legacy:
  ``services.model_credential_service``).
- When the optional AutoGen packages are missing, ``initialize_agent_service``
  no-ops gracefully (returns ``None``) instead of raising at boot.
- The legacy module-level instance was kept "accessible by Temporal worker
  activities" — the new backend has no Temporal worker, but the accessor
  remains for API handlers (see :func:`get_agent_service`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from app.agents import credentials as credential_store
from app.agents import model_config_adapter
from app.agents.autogen_compat import AUTOGEN_AVAILABLE
from app.agents.config import AgentServiceConfig
from app.agents.mcp.mcp_config_schema import MCPServerConfig
from app.agents.mcp.seed_mcp_configs import get_seed_configs

if TYPE_CHECKING:
    from app.agents.service import AutogenAgentService

logger = logging.getLogger(__name__)

# Module-level instance — shared by API handlers within one process.
_service_instance: Optional["AutogenAgentService"] = None


def get_agent_service() -> Optional["AutogenAgentService"]:
    """Return the initialized service instance (or None)."""
    return _service_instance


async def initialize_agent_service() -> Optional["AutogenAgentService"]:
    """
    Initialize the Autogen Agent Service at application startup.

    This function:
    1. Loads all model configurations into memory cache
    2. Loads and decrypts credentials
    3. Loads MCP server configurations
    4. Creates and returns the service instance

    Returns:
        Initialized AutogenAgentService instance, or ``None`` when the
        optional AutoGen dependencies are not installed (graceful no-op).
    """
    global _service_instance

    if not AUTOGEN_AVAILABLE:
        logger.warning(
            "Agent service NOT initialized: AutoGen dependencies are not installed. "
            "Agentic endpoints will return 503 until they are."
        )
        return None

    logger.info("Initializing Autogen Agent Service...")

    # Imported here so this module stays importable without AutoGen.
    from app.agents.service import AutogenAgentService

    # Create service config
    config = AgentServiceConfig()

    try:
        # 1. Load model configurations (from the `ai_models` table)
        logger.info("Loading model configurations...")
        model_configs_dict = await model_config_adapter.get_all_model_configs_dict()

        for model_name, model_config in model_configs_dict.items():
            config.model_cache.set(model_name, model_config)

        config.model_cache.loaded_at = datetime.now(timezone.utc)
        logger.info(f"Loaded {len(model_configs_dict)} model configurations")

        # 2. Load credentials
        logger.info("Loading credentials...")
        credentials_dict = await credential_store.get_all_credentials_dict()
        for provider, cred_data in credentials_dict.items():
            config.credential_cache.set_credential(
                provider=provider,
                api_key=cred_data["api_key"],
                endpoint=cred_data.get("endpoint"),
            )

        config.credential_cache.loaded_at = datetime.now(timezone.utc)
        logger.info(f"Loaded credentials for {len(credentials_dict)} providers")

        # 3. Load MCP configurations
        if config.enable_mcp:
            logger.info("Loading MCP configurations...")
            mcp_count = await _load_mcp_configs(config)
            logger.info(f"Loaded {mcp_count} MCP server configurations")

        # 4. Create service instance
        service = AutogenAgentService(config=config)

        # 5. Load MCP servers into manager
        if config.enable_mcp:
            for _server_id, server_config_dict in config.mcp_cache.servers.items():
                mcp_config = MCPServerConfig(**server_config_dict)
                service.mcp_manager.load_server(mcp_config)

        logger.info("Autogen Agent Service initialized successfully")
        logger.info(f"   - Model configs: {len(config.model_cache.configs)}")
        logger.info(f"   - Credentials: {len(config.credential_cache.credentials)}")
        logger.info(f"   - MCP servers: {len(config.mcp_cache.servers)}")

        _service_instance = service
        return service

    except Exception as e:
        logger.error(f"Failed to initialize Autogen Agent Service: {e}")
        raise


async def _load_mcp_configs(config: AgentServiceConfig) -> int:
    """
    Load MCP configurations from database (or seed if empty).

    Args:
        config: Service configuration

    Returns:
        Number of configs loaded
    """
    # TODO: Load from database when mcp_config_service is implemented
    # For MVP, use seed configurations

    seed_configs = get_seed_configs()

    for seed_config in seed_configs:
        config.mcp_cache.add_server(
            server_id=seed_config["server_id"],
            config=seed_config,
        )

    config.mcp_cache.loaded_at = datetime.now(timezone.utc)

    return len(seed_configs)


async def shutdown_agent_service(service: Optional["AutogenAgentService"] = None) -> None:
    """
    Gracefully shutdown the agent service.

    Args:
        service: Service instance to shutdown (defaults to the module-level
            instance). No-ops when nothing was initialized.
    """
    global _service_instance

    target = service or _service_instance
    if target is None:
        logger.debug("Agent service shutdown: nothing to do (not initialized)")
        return

    logger.info("Shutting down Autogen Agent Service...")

    try:
        await target.shutdown()
        logger.info("Autogen Agent Service shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        if target is _service_instance:
            _service_instance = None
