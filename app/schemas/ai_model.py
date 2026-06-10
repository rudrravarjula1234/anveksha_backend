"""AI model configuration schemas.

Mirrors the frontend mock contract (`AdminModel` from
`anveksha_ui/src/mocks/data/adminWorkflow.ts`). Field names + JSON shape
are intentionally identical so the frontend's typed hooks can talk to
this service with no transformation.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

ModelProvider = Literal[
    "Anthropic",
    "OpenAI",
    "Azure OpenAI",
    "Google Vertex",
    "AWS Bedrock",
    "Custom",
]

ModelStatus = Literal["active", "inactive"]


class AdminModelCreate(AppModel):
    """Body for `POST /api/admin/models`."""

    name: str = Field(min_length=1, max_length=120)
    provider: ModelProvider
    endpoint: str = ""
    model: str = Field(min_length=1, max_length=120, description="Provider-side model identifier")
    contextWindow: int = Field(default=8192, ge=1)
    latencyMs: int = Field(default=0, ge=0)
    costPer1kIn: float = Field(default=0.0, ge=0.0)
    costPer1kOut: float = Field(default=0.0, ge=0.0)
    fallbackId: Optional[str] = None
    notes: str = ""


class AdminModelUpdate(AppModel):
    """Body for `PATCH /api/admin/models/{id}`. All fields optional."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    provider: Optional[ModelProvider] = None
    endpoint: Optional[str] = None
    model: Optional[str] = Field(default=None, min_length=1, max_length=120)
    contextWindow: Optional[int] = Field(default=None, ge=1)
    status: Optional[ModelStatus] = None
    latencyMs: Optional[int] = Field(default=None, ge=0)
    costPer1kIn: Optional[float] = Field(default=None, ge=0.0)
    costPer1kOut: Optional[float] = Field(default=None, ge=0.0)
    fallbackId: Optional[str] = None
    notes: Optional[str] = None


class AdminModel(ReadModel):
    """The shape returned from list / create / update / toggle."""

    id: str
    name: str
    provider: ModelProvider
    endpoint: str = ""
    model: str
    contextWindow: int = 8192
    status: ModelStatus = "active"
    latencyMs: int = 0
    costPer1kIn: float = 0.0
    costPer1kOut: float = 0.0
    fallbackId: Optional[str] = None
    notes: str = ""
