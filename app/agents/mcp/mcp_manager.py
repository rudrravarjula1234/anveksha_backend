"""MCP Manager for handling MCP server connections and queries.

Ported unchanged from ``backend/lib/agent_service/mcp/mcp_manager.py``.
The actual MCP wire protocol remains a simulated MVP, exactly as in the
legacy code (see the TODO markers).
"""

import logging
from typing import Any, Dict, List, Optional

from app.agents.exceptions import MCPError

from .mcp_config_schema import MCPServerConfig
from .seed_mcp_configs import get_mcps_for_skills

logger = logging.getLogger(__name__)


class MCPManager:
    """
    Manager for MCP (Model Context Protocol) servers.

    Handles:
    - Loading MCP configurations
    - Selecting appropriate MCPs based on interview skills
    - Querying MCP servers for documentation and resources
    - Managing server connections
    """

    def __init__(self):
        """Initialize MCP Manager"""
        self.servers: Dict[str, MCPServerConfig] = {}
        self.skill_mapping: Dict[str, List[str]] = {}  # skill -> [server_ids]
        self.connected_servers: set = set()

    def load_server(self, config: MCPServerConfig):
        """
        Load an MCP server configuration.

        Args:
            config: MCP server configuration
        """
        self.servers[config.server_id] = config

        # Update skill mapping
        for skill in config.associated_skills:
            if skill not in self.skill_mapping:
                self.skill_mapping[skill] = []
            if config.server_id not in self.skill_mapping[skill]:
                self.skill_mapping[skill].append(config.server_id)

    def load_servers(self, configs: List[MCPServerConfig]):
        """
        Load multiple MCP server configurations.

        Args:
            configs: List of MCP server configurations
        """
        for config in configs:
            self.load_server(config)

    def select_servers_by_skills(self, skills: List[str]) -> List[str]:
        """
        Select appropriate MCP servers based on skills.

        Args:
            skills: List of skill names

        Returns:
            List of relevant MCP server IDs
        """
        if not skills:
            return []

        # Use seed config helper
        server_ids = get_mcps_for_skills(skills)

        # Filter to only loaded and active servers
        available_servers = [
            sid for sid in server_ids if sid in self.servers and self.servers[sid].is_active
        ]

        return available_servers

    async def connect_to_server(self, server_id: str) -> bool:
        """
        Connect to an MCP server.

        Args:
            server_id: Server ID to connect to

        Returns:
            True if connected successfully
        """
        if server_id not in self.servers:
            logger.warning(f"MCP server not found: {server_id}")
            return False

        config = self.servers[server_id]

        # TODO: Implement actual MCP connection
        # For MVP, we'll simulate connection
        logger.info(f"Connecting to MCP server: {config.name} ({config.server_url})")

        # Simulate successful connection
        self.connected_servers.add(server_id)
        return True

    async def query_server(
        self,
        server_id: str,
        query: str,
        capability: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query an MCP server for resources.

        Args:
            server_id: Server ID to query
            query: Query string
            capability: Optional capability filter (documentation, code_search, etc.)

        Returns:
            Dict with query results
        """
        if server_id not in self.servers:
            raise MCPError(f"MCP server not found: {server_id}")

        if server_id not in self.connected_servers:
            connected = await self.connect_to_server(server_id)
            if not connected:
                raise MCPError(f"Failed to connect to MCP server: {server_id}")

        config = self.servers[server_id]

        # TODO: Implement actual MCP query protocol
        # For MVP, return simulated response
        logger.info(f"Querying MCP server {config.name} with: {query}")

        return {
            "server_id": server_id,
            "server_name": config.name,
            "query": query,
            "capability": capability,
            "results": [
                {
                    "type": "documentation",
                    "title": f"Documentation for: {query}",
                    "content": f"[MCP {config.name}] Relevant documentation and examples for {query}",
                    "source": config.server_url,
                }
            ],
        }

    async def query_multiple_servers(
        self,
        server_ids: List[str],
        query: str,
        capability: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query multiple MCP servers.

        Args:
            server_ids: List of server IDs to query
            query: Query string
            capability: Optional capability filter

        Returns:
            List of query results from all servers
        """
        results = []

        for server_id in server_ids:
            try:
                result = await self.query_server(server_id, query, capability)
                results.append(result)
            except MCPError as e:
                logger.warning(f"Failed to query MCP server {server_id}: {e}")
                continue

        return results

    def get_server_info(self, server_id: str) -> Optional[MCPServerConfig]:
        """Get configuration for a specific server"""
        return self.servers.get(server_id)

    def list_servers(self, active_only: bool = True) -> List[MCPServerConfig]:
        """List all loaded MCP servers"""
        if active_only:
            return [config for config in self.servers.values() if config.is_active]
        return list(self.servers.values())

    def is_connected(self, server_id: str) -> bool:
        """Check if connected to a server"""
        return server_id in self.connected_servers

    async def disconnect_all(self):
        """Disconnect from all MCP servers"""
        # TODO: Implement actual disconnection
        logger.info("Disconnecting from all MCP servers")
        self.connected_servers.clear()
