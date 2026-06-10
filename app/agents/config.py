"""Configuration management for Agent Service.

Ported unchanged from ``backend/lib/agent_service/config.py`` — pure
in-memory cache dataclasses with no external dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ModelConfigCache:
    """In-memory cache for model configurations loaded at startup"""

    configs: Dict[str, Any] = field(default_factory=dict)
    loaded_at: Optional[datetime] = None

    def get(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get a model configuration by name"""
        return self.configs.get(model_name)

    def set(self, model_name: str, config: Dict[str, Any]):
        """Set a model configuration"""
        self.configs[model_name] = config

    def is_loaded(self) -> bool:
        """Check if configs have been loaded"""
        return self.loaded_at is not None

    def clear(self):
        """Clear the cache"""
        self.configs.clear()
        self.loaded_at = None


@dataclass
class CredentialCache:
    """In-memory cache for API credentials"""

    credentials: Dict[str, str] = field(default_factory=dict)  # provider -> api_key
    endpoints: Dict[str, Optional[str]] = field(default_factory=dict)  # provider -> endpoint
    loaded_at: Optional[datetime] = None

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider"""
        return self.credentials.get(provider)

    def get_endpoint(self, provider: str) -> Optional[str]:
        """Get custom endpoint for a provider"""
        return self.endpoints.get(provider)

    def set_credential(self, provider: str, api_key: str, endpoint: Optional[str] = None):
        """Set credential for a provider"""
        self.credentials[provider] = api_key
        if endpoint:
            self.endpoints[provider] = endpoint

    def is_loaded(self) -> bool:
        """Check if credentials have been loaded"""
        return self.loaded_at is not None


@dataclass
class MCPServerCache:
    """Cache for MCP server configurations"""

    servers: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # server_id -> config
    skill_mapping: Dict[str, list] = field(default_factory=dict)  # skill -> [server_ids]
    loaded_at: Optional[datetime] = None

    def get_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get MCP server configuration"""
        return self.servers.get(server_id)

    def get_servers_by_skill(self, skill: str) -> list:
        """Get MCP server IDs for a skill"""
        return self.skill_mapping.get(skill, [])

    def add_server(self, server_id: str, config: Dict[str, Any]):
        """Add MCP server to cache"""
        self.servers[server_id] = config

        # Update skill mapping
        for skill in config.get("associated_skills", []):
            if skill not in self.skill_mapping:
                self.skill_mapping[skill] = []
            if server_id not in self.skill_mapping[skill]:
                self.skill_mapping[skill].append(server_id)

    def is_loaded(self) -> bool:
        """Check if MCP configs have been loaded"""
        return self.loaded_at is not None


@dataclass
class AgentServiceConfig:
    """Main configuration for the Agent Service"""

    # Caches
    model_cache: ModelConfigCache = field(default_factory=ModelConfigCache)
    credential_cache: CredentialCache = field(default_factory=CredentialCache)
    mcp_cache: MCPServerCache = field(default_factory=MCPServerCache)

    # Settings
    default_max_rounds: int = 10
    default_timeout: int = 300  # seconds
    enable_token_tracking: bool = True
    enable_mcp: bool = True

    # Encryption key for credentials (should be from environment)
    encryption_key: Optional[str] = None

    def is_initialized(self) -> bool:
        """Check if all caches are loaded"""
        return (
            self.model_cache.is_loaded()
            and self.credential_cache.is_loaded()
            and (self.mcp_cache.is_loaded() if self.enable_mcp else True)
        )
