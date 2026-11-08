"""HTTP layer for `/api/admin/bots`.

Mirrors the AI-models router. See its module docstring for the contract
shape — the only difference is referential validation: a bot's
`primaryModelId` / `fallbackModelId` must point at real AI models, and
the service layer enforces that.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_roles
from app.db.session import get_session
from app.schemas.bot import BotFull, BotFullCreate, BotFullUpdate
from app.services.bot_service import BotService

router = APIRouter(
    tags=["Admin · Bots"],
    dependencies=[Depends(require_roles("admin"))],
)


def _service(db: AsyncSession = Depends(get_session)) -> BotService:
    return BotService(db)


@router.get("", response_model=list[BotFull])
async def list_bots(service: BotService = Depends(_service)) -> list[BotFull]:
    return await service.list_bots()


@router.post("", response_model=BotFull, status_code=status.HTTP_201_CREATED)
async def create_bot(
    payload: BotFullCreate,
    service: BotService = Depends(_service),
) -> BotFull:
    return await service.create(payload)


@router.patch("/{bot_id}", response_model=BotFull)
async def update_bot(
    bot_id: str,
    patch: BotFullUpdate,
    service: BotService = Depends(_service),
) -> BotFull:
    return await service.update(bot_id, patch)


@router.post("/{bot_id}/toggle", response_model=BotFull)
async def toggle_bot(
    bot_id: str,
    service: BotService = Depends(_service),
) -> BotFull:
    return await service.toggle_status(bot_id)


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: str,
    service: BotService = Depends(_service),
) -> None:
    await service.delete(bot_id)
