"""Seed MCP configurations for skills mapping.

Ported unchanged from ``backend/lib/agent_service/mcp/seed_mcp_configs.py``.
"""

from typing import Any, Dict, List

# Mapping of skills to MCP server IDs
SKILL_TO_MCP_MAPPING: Dict[str, List[str]] = {
    # Add skill to MCP server ID mappings here
    # Example: "python": ["python-mcp-server"]
}

# Seed configurations for MCP servers
SEED_MCP_CONFIGS: List[Dict[str, Any]] = [
    {
        "server_id": "mdn-docs",
        "name": "MDN Web Docs",
        "server_url": "http://localhost:3001",
        "auth_type": "none",
        "auth_config": {},
        "capabilities": ["documentation", "web-apis"],
        "description": "MDN documentation for web technologies",
        "skills": ["web-development", "html", "css", "javascript"],
        "is_active": True,
    },
    {
        "server_id": "github-docs",
        "name": "GitHub Documentation",
        "server_url": "http://localhost:3002",
        "auth_type": "none",
        "auth_config": {},
        "capabilities": ["documentation", "code-search"],
        "description": "GitHub documentation and API reference",
        "skills": ["git", "github", "version-control"],
        "is_active": True,
    },
    {
        "server_id": "stack-overflow",
        "name": "Stack Overflow",
        "server_url": "http://localhost:3003",
        "auth_type": "none",
        "auth_config": {},
        "capabilities": ["qa", "code-examples"],
        "description": "Stack Overflow Q&A and code examples",
        "skills": ["general", "troubleshooting"],
        "is_active": True,
    },
]


def get_mcps_for_skills(skills: List[str]) -> List[str]:
    """
    Get list of MCP server IDs for given skills.

    Args:
        skills: List of skill names

    Returns:
        List of MCP server IDs that support the given skills
    """
    if not skills:
        return []

    mcp_servers = set()
    for skill in skills:
        if skill in SKILL_TO_MCP_MAPPING:
            mcp_servers.update(SKILL_TO_MCP_MAPPING[skill])

    return list(mcp_servers)


def get_seed_configs() -> List[Dict[str, Any]]:
    """
    Get seed MCP configurations.

    Returns:
        List of MCP server configurations
    """
    return SEED_MCP_CONFIGS
