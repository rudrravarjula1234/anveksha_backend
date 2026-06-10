"""MCP tools integration for autogen 0.7.5

Ported unchanged from ``backend/lib/agent_service/mcp/mcp_tools.py``.

Note: MCP integration in autogen 0.7.5 uses a different architecture.
Tools are registered via model clients, not agents directly.
This is a simplified version for MVP.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def create_mcp_query_tool(mcp_manager, server_ids: Optional[List[str]] = None):
    """
    Create MCP query tool for agents.

    Note: In autogen 0.7.5, tools are registered differently.
    This creates a callable function that agents can use.

    Args:
        mcp_manager: MCPManager instance
        server_ids: Specific server IDs

    Returns:
        Async function for querying MCP
    """

    async def query_documentation(topic: str, capability: str = "documentation") -> str:
        """Query MCP servers for documentation"""
        logger.info(f"MCP query: {topic}")

        servers_to_query = server_ids if server_ids else list(mcp_manager.servers.keys())

        if not servers_to_query:
            return "No MCP servers available"

        results = await mcp_manager.query_multiple_servers(
            server_ids=servers_to_query,
            query=topic,
            capability=capability,
        )

        if not results:
            return f"No documentation found for: {topic}"

        formatted = [f"Documentation for '{topic}':"]
        for result in results:
            server_name = result.get("server_name", "Unknown")
            items = result.get("results", [])
            for item in items:
                formatted.append(f"\n[{server_name}] {item.get('title', '')}")
                formatted.append(f"{item.get('content', '')[:500]}...")

        return "\n".join(formatted)

    return query_documentation


def register_mcp_tools_with_agents(
    agents: List,
    mcp_manager,
    server_ids: Optional[List[str]] = None,
    skills: Optional[List[str]] = None,
):
    """
    Register MCP tools with agents.

    Note: In autogen 0.7.5, this is handled differently.
    Tools are part of the model client configuration.
    For MVP, we'll add this to agent metadata for later use.

    Args:
        agents: List of agents
        mcp_manager: MCP manager
        server_ids: Server IDs
        skills: Skills for server selection
    """
    # For autogen 0.7.5, tool registration is done via model clients
    # This is a placeholder for future enhancement
    logger.info(f"MCP tools available for {len(agents)} agents")
    logger.info("Note: Full MCP integration requires autogen-ext[mcp] tool registration")

    # Store MCP manager reference in agents for manual calls if needed
    for agent in agents:
        if not hasattr(agent, "_mcp_manager"):
            agent._mcp_manager = mcp_manager
            agent._mcp_server_ids = server_ids
            agent._mcp_skills = skills
