"""MCP configuration schemas.

Ported from ``backend/lib/agent_service/mcp/mcp_config_schema.py``; the
database model now uses Pydantic v2 ``ConfigDict`` (the legacy v1 ``Config``
with a bson ``ObjectId`` json encoder was dropped — ids are plain strings).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server"""

    server_id: str = Field(..., description="Unique server identifier")
    name: str = Field(..., description="Human-readable name")
    server_url: str = Field(..., description="MCP server URL")

    # Authentication
    auth_type: str = Field(default="none", description="Authentication type: none, api_key, oauth")
    auth_config: Dict[str, Any] = Field(default_factory=dict, description="Auth configuration")

    # Capabilities
    capabilities: List[str] = Field(
        default_factory=list,
        description="Server capabilities: documentation, code_search, qa, etc.",
    )
    associated_skills: List[str] = Field(
        default_factory=list,
        description="Skills this MCP server supports",
    )
    tags: List[str] = Field(default_factory=list, description="Categorization tags")

    # Configuration
    connection_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Connection configuration (timeout, retries, etc.)",
    )

    # Metadata
    description: Optional[str] = Field(None, description="Server description")
    is_active: bool = Field(default=True, description="Whether server is active")
    is_seed: bool = Field(default=False, description="Whether this is a seed config")

    # Port note: the seed configs carry extra keys (e.g. "skills"); tolerate them.
    model_config = ConfigDict(extra="ignore")


class MCPServerConfigModel(BaseModel):
    """Database model for MCP server configurations"""

    id: Optional[str] = Field(alias="_id", default=None)
    server_id: str
    name: str
    server_url: str
    auth_type: str = "none"
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    capabilities: List[str] = Field(default_factory=list)
    associated_skills: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    connection_config: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    is_active: bool = True
    is_seed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
