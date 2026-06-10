"""MCP (Model Context Protocol) integration"""

from .mcp_config_schema import MCPServerConfig
from .mcp_manager import MCPManager

__all__ = ["MCPManager", "MCPServerConfig"]
