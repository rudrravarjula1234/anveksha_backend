"""Bot schemas — mirror of the frontend's `BotFull` mock contract
(`anveksha_ui/src/mocks/data/botsFull.ts`), camelCase preserved on the
wire. `primaryModelId` / `fallbackModelId` are FK-enforced references to
`ai_models` at the database layer.
"""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

BotStatus = Literal["active", "draft", "inactive"]


class BotFullCreate(AppModel):
    """Body for `POST /api/admin/bots`."""

    name: str = Field(min_length=1, max_length=60)
    fullName: Optional[str] = Field(default=None, max_length=200)
    avatar: Optional[str] = Field(default=None, max_length=4)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    specializations: list[str] = Field(default_factory=list)
    primaryModelId: str = Field(min_length=1)
    fallbackModelId: Optional[str] = None
    persona: str = ""
    systemPrompt: str = ""


class BotFullUpdate(AppModel):
    """Body for `PATCH /api/admin/bots/{id}`. All fields optional."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    fullName: Optional[str] = Field(default=None, max_length=200)
    avatar: Optional[str] = Field(default=None, max_length=4)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    specializations: Optional[list[str]] = None
    primaryModelId: Optional[str] = None
    fallbackModelId: Optional[str] = None
    persona: Optional[str] = None
    systemPrompt: Optional[str] = None
    status: Optional[BotStatus] = None


class BotFull(ReadModel):
    """The shape returned from list / create / update / toggle."""

    id: str
    name: str
    fullName: str
    avatar: str
    color: str
    specializations: list[str] = Field(default_factory=list)
    primaryModelId: str
    fallbackModelId: Optional[str] = None
    persona: str = ""
    systemPrompt: str = ""
    status: BotStatus = "active"
    sessionsRun: int = 0
    avgScore: float = 0.0
