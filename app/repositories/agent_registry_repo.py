"""Repository for the agent registry (Postgres)."""

from app.models.agent_registry import AgentConfig
from app.repositories.sql_base import SqlRepository


class AgentRegistryRepository(SqlRepository[AgentConfig]):
    model = AgentConfig
