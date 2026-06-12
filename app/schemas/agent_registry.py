"""Agent registry schemas.

Tatvo ships a fixed set of PRE-DEFINED agents (brief generation,
report generation, gap/gray analysis, candidate search, candidate chat).
Admins can re-point each agent at a different AI model and edit its
system message — both stored in Mongo. The registry rows are config,
not runtime state.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

# Stable identifiers — the execution layer looks agents up by these.
AgentId = Literal[
    "interviewer_brief",
    "report_generator",
    "gap_analyzer",
    "gray_analyzer",
    "candidate_search",
    "candidate_chat",
]


class AgentConfig(ReadModel):
    id: AgentId
    name: str
    description: str
    # Where this agent is invoked from — surfaced in the admin UI.
    usedBy: list[str] = Field(default_factory=list)
    # Reference into the ai_models collection. None → first active model.
    modelId: Optional[str] = None
    systemMessage: str
    # The shipped default, kept alongside so admins can reset.
    defaultSystemMessage: str
    temperature: float = 0.4
    enabled: bool = True
    updatedAt: Optional[str] = None
    updatedBy: Optional[str] = None


class AgentConfigPatch(AppModel):
    modelId: Optional[str] = None
    systemMessage: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    enabled: Optional[bool] = None


class AgentRunResult(ReadModel):
    """Uniform envelope for agent executions.

    `source` tells the caller whether the text came from a real model run
    or the deterministic fallback (no credentials / framework disabled).
    """

    agentId: str
    output: str
    source: Literal["agent", "fallback"]
    modelId: Optional[str] = None
