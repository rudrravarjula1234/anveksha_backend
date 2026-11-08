"""Business logic for bots (rich view — /api/admin/bots, BotFull).

Carries the only piece of cross-collection validation we have today —
`primaryModelId` and `fallbackModelId` must reference real AI models.
Centralising that here keeps the API layer ignorant of the constraint.

`bots` is a merged table also written by the "simple" view
(app.services.admin_ops_service.AdminOpsService.simple_bots /
create_simple_bot) — a row created there won't have full_name/avatar/
color set, so `_to_schema` derives the same fallbacks `create()` uses at
write time, applied again at read time, so BotFull's required fields are
always satisfiable regardless of which surface created the row.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import bot_id
from app.models.bot import Bot as BotModel
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

# Statuses that exist only on the simple view's vocabulary — BotFull
# doesn't know them; fold to the closest rich-view equivalent on read.
_STATUS_TO_FULL = {"paused": "inactive"}


def _palette_color(bot_string_id: str) -> str:
    """Deterministically derive a palette color from a bot id."""
    h = sum(ord(c) for c in bot_string_id) if bot_string_id else 0
    return _BOT_PALETTE[h % len(_BOT_PALETTE)]


def _avatar_letter(name: str) -> str:
    return (name[:1] or "?").upper()


def _to_schema(row: BotModel) -> BotFull:
    return BotFull(
        id=row.id,
        name=row.name,
        fullName=row.full_name or row.name,
        avatar=row.avatar or _avatar_letter(row.name),
        color=row.color or _palette_color(row.id),
        specializations=list(row.specializations or []),
        primaryModelId=row.primary_model_id or "",
        fallbackModelId=row.fallback_model_id,
        persona=row.persona,
        systemPrompt=row.system_prompt,
        status=_STATUS_TO_FULL.get(row.status, row.status),  # type: ignore[arg-type]
        sessionsRun=row.sessions_run,
        avgScore=row.avg_score,
    )


class BotService:
    def __init__(
        self,
        db: AsyncSession,
        repo: Optional[BotRepository] = None,
        models_repo: Optional[AIModelRepository] = None,
    ) -> None:
        self.repo = repo or BotRepository(db)
        self.models_repo = models_repo or AIModelRepository(db)

    async def list_bots(self) -> list[BotFull]:
        rows = await self.repo.list_all()
        return [_to_schema(r) for r in rows]

    async def get(self, item_id: str) -> BotFull:
        row = await self.repo.find_by_id(item_id)
        if row is None:
            raise NotFoundError(f"Bot {item_id} not found")
        return _to_schema(row)

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
        # Referential checks first — fail before we write anything.
        await self._assert_model_exists(payload.primaryModelId, field="primaryModelId")
        await self._assert_model_exists(payload.fallbackModelId, field="fallbackModelId")

        new_id = bot_id()
        row = await self.repo.insert(
            id=new_id,
            name=payload.name,
            full_name=payload.fullName or payload.name,
            avatar=payload.avatar or _avatar_letter(payload.name),
            color=payload.color or _palette_color(new_id),
            specializations=payload.specializations,
            primary_model_id=payload.primaryModelId,
            fallback_model_id=payload.fallbackModelId,
            persona=payload.persona,
            system_prompt=payload.systemPrompt,
            status="draft",  # bots start as draft until enabled
            sessions_run=0,
            avg_score=0.0,
        )
        return _to_schema(row)

    async def update(self, item_id: str, patch: BotFullUpdate) -> BotFull:
        if patch.primaryModelId is not None:
            await self._assert_model_exists(patch.primaryModelId, field="primaryModelId")
        if patch.fallbackModelId is not None:
            await self._assert_model_exists(patch.fallbackModelId, field="fallbackModelId")

        diff = patch.model_dump(exclude_unset=True)
        # camelCase (API) -> snake_case (ORM column), rich-view fields only.
        field_map = {
            "name": "name",
            "fullName": "full_name",
            "avatar": "avatar",
            "color": "color",
            "specializations": "specializations",
            "primaryModelId": "primary_model_id",
            "fallbackModelId": "fallback_model_id",
            "persona": "persona",
            "systemPrompt": "system_prompt",
            "status": "status",
        }
        kwargs = {field_map[k]: v for k, v in diff.items() if k in field_map}
        row = await self.repo.update_by_id(item_id, **kwargs)
        if row is None:
            raise NotFoundError(f"Bot {item_id} not found")
        return _to_schema(row)

    async def toggle_status(self, item_id: str) -> BotFull:
        """Cycle status. Convention:
        - active   → inactive
        - inactive → active
        - draft    → active   (a draft can be 'turned on')
        - paused   → active   (simple-view status, folds to the same rule)
        """
        current = await self.get(item_id)
        next_status = "inactive" if current.status == "active" else "active"
        return await self.update(item_id, BotFullUpdate(status=next_status))

    async def delete(self, item_id: str) -> None:
        removed = await self.repo.delete_by_id(item_id)
        if not removed:
            raise NotFoundError(f"Bot {item_id} not found")
