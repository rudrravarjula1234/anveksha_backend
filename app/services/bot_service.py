"""Business logic for bots.

Carries the only piece of cross-collection validation we have today —
`primaryModelId` and `fallbackModelId` must reference real AI models.
Centralising that here keeps the API layer ignorant of the constraint.
"""

from typing import Optional

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import bot_id
from app.repositories.ai_model_repo import AIModelRepository
from app.repositories.bot_repo import BotRepository
from app.schemas.bot import BotFull, BotFullCreate, BotFullUpdate

# Reuse the frontend's BOT_PALETTE so default colors line up with the UI's
# visual identity (anveksha_ui/src/mocks/data/botsFull.ts).
_BOT_PALETTE = [
    "#2F5E3E",
    "#2F4E78",
    "#8B2A2A",
    "#5B3E8F",
    "#7A4915",
    "#3D5A7A",
    "#4A6B3E",
    "#141310",
]


def _palette_color(bot_string_id: str) -> str:
    """Deterministically derive a palette color from a bot id."""
    h = sum(ord(c) for c in bot_string_id) if bot_string_id else 0
    return _BOT_PALETTE[h % len(_BOT_PALETTE)]


def _avatar_letter(name: str) -> str:
    return (name[:1] or "?").upper()


class BotService:
    def __init__(
        self,
        repo: Optional[BotRepository] = None,
        models_repo: Optional[AIModelRepository] = None,
    ) -> None:
        self.repo = repo or BotRepository()
        self.models_repo = models_repo or AIModelRepository()

    async def list_bots(self) -> list[BotFull]:
        return await self.repo.list_all()

    async def get(self, item_id: str) -> BotFull:
        bot = await self.repo.find_by_id(item_id)
        if bot is None:
            raise NotFoundError(f"Bot {item_id} not found")
        return bot

    async def _assert_model_exists(self, model_id_value: Optional[str], *, field: str) -> None:
        if model_id_value is None:
            return
        model = await self.models_repo.find_by_id(model_id_value)
        if model is None:
            raise ValidationError(
                f"{field}={model_id_value} does not match any AI model",
                extra={"field": field, "id": model_id_value},
            )

    async def create(self, payload: BotFullCreate) -> BotFull:
        # Referential checks first — fail before we mutate Mongo.
        await self._assert_model_exists(payload.primaryModelId, field="primaryModelId")
        await self._assert_model_exists(payload.fallbackModelId, field="fallbackModelId")

        new_id = bot_id()
        doc = payload.model_dump()
        doc["id"] = new_id
        doc.setdefault("status", "draft")  # bots start as draft until enabled
        doc["fullName"] = doc.get("fullName") or payload.name
        doc["avatar"] = doc.get("avatar") or _avatar_letter(payload.name)
        doc["color"] = doc.get("color") or _palette_color(new_id)
        doc.setdefault("sessionsRun", 0)
        doc.setdefault("avgScore", 0.0)
        return await self.repo.insert(doc)

    async def update(self, item_id: str, patch: BotFullUpdate) -> BotFull:
        if patch.primaryModelId is not None:
            await self._assert_model_exists(patch.primaryModelId, field="primaryModelId")
        if patch.fallbackModelId is not None:
            await self._assert_model_exists(patch.fallbackModelId, field="fallbackModelId")

        diff = patch.model_dump(exclude_unset=True)
        updated = await self.repo.update_by_id(item_id, diff)
        if updated is None:
            raise NotFoundError(f"Bot {item_id} not found")
        return updated

    async def toggle_status(self, item_id: str) -> BotFull:
        """Cycle status. Convention:
        - active   → inactive
        - inactive → active
        - draft    → active   (a draft can be 'turned on')
        """
        current = await self.get(item_id)
        if current.status == "active":
            next_status = "inactive"
        else:
            next_status = "active"
        return await self.update(item_id, BotFullUpdate(status=next_status))

    async def delete(self, item_id: str) -> None:
        removed = await self.repo.delete_by_id(item_id)
        if not removed:
            raise NotFoundError(f"Bot {item_id} not found")
