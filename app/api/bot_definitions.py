"""Public bot-definition endpoint for the RAW bot-worker.

RAW's bot-worker (a service, not a logged-in user) resolves a bot's persona
fresh at join time — see RAW_App/bot-worker/anveksha.py's
``fetch_bot_definition``. This is the real replacement for that file's local
``mock_bots`` registry: one unauthenticated GET that returns the seeded
persona / system prompt for a bot id.

Persona text is not sensitive (it's what the bot says about itself in the
room), so this is deliberately open — no user token to thread through a
room-join → Temporal → bot-worker call chain. It only ever reads.
"""

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.base import ReadModel
from app.services.bot_service import BotService

router = APIRouter(tags=["Bots (definition)"])


class BotDefinitionWire(ReadModel):
    """The exact shape RAW's bot-worker maps to its BotDefinition dataclass."""

    botId: str
    name: str
    persona: str = ""
    systemPrompt: str = Field(default="")


@router.get("/{bot_id}/definition", response_model=BotDefinitionWire)
async def get_bot_definition(bot_id: str, db: AsyncSession = Depends(get_session)) -> BotDefinitionWire:
    bot = await BotService(db).get(bot_id)  # raises NotFoundError -> 404
    return BotDefinitionWire(
        botId=bot.id,
        name=bot.fullName or bot.name,
        persona=bot.persona or "",
        systemPrompt=bot.systemPrompt or "",
    )
