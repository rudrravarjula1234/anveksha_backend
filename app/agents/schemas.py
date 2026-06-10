"""Pydantic schemas for the agent framework.

Consolidates three legacy modules into one (all Pydantic v2):

- ``backend/lib/agent_service/schemas.py``      (orchestration configs / HITL / streaming)
- ``backend/schemas/token_usage.py``            (token usage records)
- ``backend/schemas/interview_feedback_schemas.py`` (feedback request/response)

plus the new credential API models for ``app/api/agents.py``.

Port notes:
- v1 ``@validator`` -> v2 ``@field_validator`` (``pre=True`` -> ``mode="before"``).
- ``min_items`` -> ``min_length``; ``Field(example=...)`` -> ``examples=[...]``.
- ``DetailedAnalysis.gap_analysis`` now defaults to ``""`` — the hierarchical
  coordinator prompt does not emit it (only the direct-call prompt does), so a
  required field would reject otherwise-valid orchestration output.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import AppModel, ReadModel

# ─────────────────────────────────────────────────────────────────────────
# Orchestration / HITL / streaming schemas
# ─────────────────────────────────────────────────────────────────────────


class HumanInputMode(str, Enum):
    """Mode for human-in-the-loop interaction"""

    NEVER = "never"  # Never request human input
    ON_DEMAND = "on_demand"  # Agent can request human input when needed
    STEP_APPROVAL = "step_approval"  # Require human approval before each step
    EVERY_MESSAGE = "every_message"  # Human reviews every message


class StreamEventType(str, Enum):
    """Types of streaming events"""

    TOKEN = "token"  # Individual token from model
    MESSAGE = "message"  # Complete message from agent
    STATUS = "status"  # Status update (started, waiting, completed)
    HUMAN_INPUT_REQUEST = "human_input_request"  # Waiting for human input
    ERROR = "error"  # Error event


class HumanInputRequest(BaseModel):
    """Request for human input during orchestration"""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context: str = Field(..., description="Current conversation context")
    prompt_for_human: str = Field(..., description="What to ask the human")
    agent_name: str = Field(..., description="Name of agent requesting input")
    options: Optional[List[str]] = Field(None, description="Optional predefined choices")
    timeout_seconds: int = Field(default=300, description="Timeout for human response")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HumanInputResponse(BaseModel):
    """Human's response to an input request"""

    request_id: str = Field(..., description="ID of the original request")
    content: str = Field(..., description="Human's input content")
    action: str = Field(default="continue", description="Action: continue, abort, retry")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StreamEvent(BaseModel):
    """A streaming event during orchestration"""

    event_type: StreamEventType
    content: str = Field(default="")
    source: Optional[str] = Field(None, description="Source agent name")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[float] = Field(None, description="Event timestamp")


class AgentConfig(BaseModel):
    """
    Configuration for a single agent in orchestration.

    This is passed directly to the service instead of fetching from database.
    """

    # `model_name` collides with Pydantic v2's protected "model_" namespace;
    # disable it to keep the legacy field names without warnings.
    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(..., description="Agent name")
    model_name: str = Field(..., description="Model to use (e.g., 'gpt-4', 'llama2')")
    system_message: str = Field(..., description="System message/prompt for the agent")

    # Optional agent-specific settings
    role: Optional[str] = Field(
        None, description="Role in orchestration: coordinator, specialist, critic, etc."
    )
    associated_skills: List[str] = Field(
        default_factory=list, description="Skills this agent specializes in"
    )

    # Human actor configuration
    is_human_actor: bool = Field(
        default=False, description="Whether this agent represents a human participant"
    )
    human_input_mode: HumanInputMode = Field(
        default=HumanInputMode.NEVER, description="When to request human input"
    )

    # Autogen-specific config
    max_consecutive_auto_reply: Optional[int] = Field(None, description="Max auto-replies")
    code_execution_config: bool = Field(default=False, description="Enable code execution")

    # MCP preferences
    can_use_mcp: bool = Field(default=True, description="Whether agent can call MCP tools")
    preferred_mcp_servers: List[str] = Field(
        default_factory=list, description="Preferred MCP server IDs"
    )

    # Additional configuration
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("human_input_mode", mode="before")
    @classmethod
    def normalize_human_input_mode(cls, v: Any) -> Any:
        """Legacy agent configs used uppercase mode names (e.g. ``"NEVER"``)."""
        if isinstance(v, str):
            return v.lower()
        return v


class OrchestrationConfig(BaseModel):
    """
    Configuration for orchestration patterns.

    Passed to orchestration methods to control behavior.
    """

    orchestration_type: str = Field(
        ..., description="round_robin, group_chat, workflow, or hierarchical"
    )
    agents: List[AgentConfig] = Field(..., description="List of agent configurations")

    # General settings
    max_rounds: int = Field(default=10, description="Maximum conversation rounds")

    # Group chat specific
    speaker_selection_method: str = Field(default="auto", description="auto, round_robin, manual")

    # Workflow specific
    workflow_steps: Optional[List[dict[str, Any]]] = Field(
        None, description="Workflow steps with agent assignments"
    )

    # Hierarchical specific
    coordinator_agent_index: Optional[int] = Field(
        None, description="Index of coordinator agent in agents list"
    )

    # MCP settings
    enable_mcp_tools: bool = Field(default=True, description="Enable MCP as agent tools")
    mcp_server_ids: Optional[List[str]] = Field(
        None, description="Specific MCP servers to make available (None = auto-select)"
    )

    # Human in the loop
    human_in_loop: bool = Field(default=False, description="Enable human intervention")
    human_agent_name: str = Field(default="Human_Reviewer", description="Name for human agent")
    human_input_timeout: int = Field(default=300, description="Timeout in seconds for human input")

    # Streaming configuration
    enable_streaming: bool = Field(default=False, description="Enable streaming responses")

    # Retry configuration for rate limiting
    retry_enabled: bool = Field(default=True, description="Enable retry on rate limit errors")
    retry_max_attempts: int = Field(default=2, description="Maximum retry attempts")
    retry_initial_delay: float = Field(default=1.0, description="Initial delay in seconds")
    retry_max_delay: float = Field(default=60.0, description="Maximum delay in seconds")

    # Metadata
    interview_id: Optional[str] = Field(None, description="Related interview ID")
    candidate_id: Optional[str] = Field(None, description="Candidate ID")
    skills_being_tested: List[str] = Field(
        default_factory=list, description="Skills being evaluated"
    )


class WorkflowStep(BaseModel):
    """Single step in a workflow"""

    step_name: str = Field(..., description="Name of this step")
    agent_index: int = Field(
        ..., description="Index of agent in agents list to use for this step"
    )
    description: Optional[str] = Field(None, description="Step description")
    success_criteria: Optional[str] = Field(
        None, description="Criteria for moving to next step"
    )
    max_turns: int = Field(default=5, description="Max turns for this step")


# ─────────────────────────────────────────────────────────────────────────
# Token usage schemas (legacy backend/schemas/token_usage.py)
# ─────────────────────────────────────────────────────────────────────────


class TokenUsageBase(BaseModel):
    """Base schema for token usage"""

    # Legacy field `model_name` collides with Pydantic v2's "model_" namespace.
    model_config = ConfigDict(protected_namespaces=())

    request_id: str = Field(..., description="Unique request identifier")
    agent_ids: List[str] = Field(default_factory=list, description="Agent IDs involved")
    model_name: str = Field(..., description="Model used")
    orchestration_type: str = Field(
        ..., description="direct, round_robin, group_chat, workflow"
    )

    # Token counts
    input_tokens: int = Field(..., ge=0, description="Number of input tokens")
    output_tokens: int = Field(..., ge=0, description="Number of output tokens")
    total_tokens: int = Field(..., ge=0, description="Total tokens used")

    # Cost calculation
    input_cost: float = Field(default=0.0, ge=0.0, description="Cost of input tokens")
    output_cost: float = Field(default=0.0, ge=0.0, description="Cost of output tokens")
    total_cost: float = Field(default=0.0, ge=0.0, description="Total cost")
    currency: str = Field(default="USD", description="Currency code")

    # Request details
    interview_id: Optional[str] = Field(None, description="Related interview ID")
    user_id: Optional[str] = Field(None, description="User who made the request")
    duration_ms: Optional[int] = Field(
        None, ge=0, description="Request duration in milliseconds"
    )


class TokenUsageCreate(TokenUsageBase):
    """Schema for creating a token usage record"""


class TokenUsage(TokenUsageBase):
    """Full token usage schema with timestamps"""

    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TokenUsageStats(BaseModel):
    """Aggregated token usage statistics"""

    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost: float
    currency: str
    average_tokens_per_request: float
    average_cost_per_request: float


# ─────────────────────────────────────────────────────────────────────────
# Interview feedback schemas (legacy backend/schemas/interview_feedback_schemas.py)
# ─────────────────────────────────────────────────────────────────────────


class InterviewMetadata(BaseModel):
    """Optional metadata about the interview context."""

    role: Optional[str] = Field(
        None,
        description="Job role being interviewed for (e.g., 'Senior Python Developer')",
        examples=["Senior Backend Engineer"],
    )
    experience_level: Optional[str] = Field(
        None,
        description="Expected experience level (e.g., 'junior', 'mid-level', 'senior')",
        pattern="^(junior|mid-level|senior|staff|principal)$",
        examples=["senior"],
    )
    tech_stack: Optional[List[str]] = Field(
        default_factory=list,
        description="Technologies/skills being evaluated",
        examples=[["python", "fastapi", "postgresql", "redis"]],
    )
    interview_type: Optional[str] = Field(
        None,
        description="Type of interview conducted",
        pattern="^(coding|system_design|behavioral|mixed)$",
        examples=["coding"],
    )
    interview_id: Optional[str] = Field(None, description="Interview ID for tracking")
    candidate_id: Optional[str] = Field(None, description="Candidate ID for tracking")


class FeedbackRequest(BaseModel):
    """Request schema for generating interview feedback."""

    transcript: str = Field(
        ...,
        min_length=10,
        description="Raw interview transcript text",
        examples=[
            "Interviewer: Can you explain how you would implement a rate limiter?"
            "\n\nCandidate: I would use a token bucket algorithm..."
        ],
    )
    metadata: Optional[InterviewMetadata] = Field(
        None, description="Optional interview context metadata"
    )

    @field_validator("transcript")
    @classmethod
    def validate_transcript_not_empty(cls, v: str) -> str:
        """Ensure transcript is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Transcript cannot be empty or whitespace only")
        return v.strip()


class DetailedAnalysis(BaseModel):
    """Detailed analysis breakdown from specialist agents."""

    transcript_summary: str = Field(
        ..., description="Summary of key points from the transcript"
    )
    technical_evaluation: str = Field(
        ..., description="Technical competency assessment summary"
    )
    communication_evaluation: str = Field(
        ..., description="Communication skills assessment summary"
    )
    key_topics_discussed: List[str] = Field(
        ..., description="List of technical topics covered in the interview"
    )
    gap_analysis: str = Field(
        default="",
        description=(
            "Analysis of skill gaps and areas for improvement based on role requirements"
        ),
    )

    @field_validator("technical_evaluation", "communication_evaluation", mode="before")
    @classmethod
    def convert_dict_to_string(cls, v: Any) -> str:
        """Convert dict/object inputs to JSON string."""
        if isinstance(v, dict):
            return json.dumps(v, indent=2)
        return str(v) if v is not None else ""


class FeedbackData(BaseModel):
    """Core feedback data structure."""

    overall_rating: float = Field(
        ..., ge=1, le=5, description="Overall rating from 1 (poor) to 5 (excellent)"
    )
    technical_skills: float = Field(
        ..., ge=1, le=5, description="Technical skills rating from 1 to 5"
    )
    communication_skills: float = Field(
        ..., ge=1, le=5, description="Communication skills rating from 1 to 5"
    )
    problem_solving: float = Field(
        ..., ge=1, le=5, description="Problem-solving ability rating from 1 to 5"
    )
    strengths: List[str] = Field(
        ..., min_length=1, description="List of candidate's key strengths"
    )
    weaknesses: List[str] = Field(
        ..., min_length=1, description="List of areas for improvement"
    )
    overall_comment: str = Field(
        ..., min_length=20, description="Comprehensive summary comment"
    )
    recommendation: str = Field(
        ...,
        pattern="^(hire|no_hire|maybe)$",
        description="Hiring recommendation: 'hire', 'no_hire', or 'maybe'",
    )
    detailed_analysis: DetailedAnalysis = Field(
        ..., description="Detailed breakdown of the analysis"
    )

    @field_validator("recommendation", mode="before")
    @classmethod
    def normalize_recommendation(cls, v: Any) -> Any:
        """Normalize recommendation values to valid options."""
        if isinstance(v, str):
            v_lower = v.lower().strip()
            # Map common variations to valid values
            if v_lower in ["hire", "yes", "strong_hire", "strong hire"]:
                return "hire"
            elif v_lower in ["no_hire", "no hire", "no", "reject"]:
                return "no_hire"
            elif v_lower in ["maybe", "consider", "uncertain", "borderline"]:
                return "maybe"
        return v


class FeedbackMetadata(BaseModel):
    """Metadata about the feedback generation process."""

    # Legacy field `model_used` collides with Pydantic v2's "model_" namespace.
    model_config = ConfigDict(protected_namespaces=())

    interview_type: Optional[str] = Field(
        None, description="Type of interview that was analyzed"
    )
    role: Optional[str] = Field(None, description="Job role being interviewed for")
    duration_ms: int = Field(
        ..., description="Time taken to generate feedback in milliseconds"
    )
    token_usage: Optional[Dict[str, Any]] = Field(
        None, description="Token usage and cost information"
    )
    model_used: str = Field(
        default="gemini-2.0-flash", description="AI model used for feedback generation"
    )


class FeedbackResponse(BaseModel):
    """Complete response schema for interview feedback."""

    feedback: FeedbackData = Field(..., description="Generated feedback data")
    metadata: FeedbackMetadata = Field(
        ..., description="Metadata about the feedback generation"
    )


# ─────────────────────────────────────────────────────────────────────────
# Credential API models (new in the port — used by app/api/agents.py)
# ─────────────────────────────────────────────────────────────────────────


class CredentialUpsert(AppModel):
    """Body for `POST /api/agents/credentials` — plaintext key, encrypted at rest."""

    provider: str = Field(
        min_length=1,
        max_length=40,
        description="Provider key: openai, azure, google, anthropic, bedrock, ollama, custom",
    )
    api_key: str = Field(min_length=1, description="API key (encrypted before storage)")
    endpoint: Optional[str] = Field(default=None, description="Custom endpoint URL")
    additional_config: Dict[str, Any] = Field(
        default_factory=dict, description="Extra provider-specific configuration"
    )

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, v: str) -> str:
        return v.strip().lower()


class CredentialMasked(ReadModel):
    """Masked credential row returned from list/upsert endpoints."""

    provider: str
    api_key_masked: str
    endpoint: Optional[str] = None
    additional_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
