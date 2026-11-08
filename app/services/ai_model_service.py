"""Business logic for AI model configurations. Mostly straight CRUD, but
the indirection leaves room for uniqueness checks, audit logging, or
cache invalidation later. Translates between the ORM row and the
camelCase `AdminModel` API schema.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import model_id
from app.models.ai_model import AIModel
from app.repositories.ai_model_repo import AIModelRepository
from app.schemas.ai_model import (
    AdminModel,
    AdminModelCreate,
    AdminModelUpdate,
)

# camelCase (API) -> snake_case (ORM column) for every writable field.
_FIELD_MAP: dict[str, str] = {
    "name": "name",
    "provider": "provider",
    "endpoint": "endpoint",
    "model": "model",
    "contextWindow": "context_window",
    "status": "status",
    "latencyMs": "latency_ms",
    "costPer1kIn": "cost_per_1k_in",
    "costPer1kOut": "cost_per_1k_out",
    "fallbackId": "fallback_id",
    "notes": "notes",
}


def _to_schema(row: AIModel) -> AdminModel:
    return AdminModel(
        id=row.id,
        name=row.name,
        provider=row.provider,
        endpoint=row.endpoint,
        model=row.model,
        contextWindow=row.context_window,
        status=row.status,
        latencyMs=row.latency_ms,
        costPer1kIn=row.cost_per_1k_in,
        costPer1kOut=row.cost_per_1k_out,
        fallbackId=row.fallback_id,
        notes=row.notes,
    )


def _to_orm_kwargs(payload: dict) -> dict:
    return {_FIELD_MAP[k]: v for k, v in payload.items() if k in _FIELD_MAP}


class AIModelService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = AIModelRepository(db)

    async def list_models(self) -> list[AdminModel]:
        # ai_models is an admin-curated config table (dozens of rows at
        # most, not user data) — a plain bounded list, not a candidate
        # for the keyset pagination high-growth tables need.
        rows = await self.repo.list_all()
        return [_to_schema(r) for r in rows]

    async def get(self, item_id: str) -> AdminModel:
        row = await self.repo.find_by_id(item_id)
        if row is None:
            raise NotFoundError(f"Model {item_id} not found")
        return _to_schema(row)

    async def create(self, payload: AdminModelCreate) -> AdminModel:
        kwargs = _to_orm_kwargs(payload.model_dump())
        kwargs["id"] = model_id()
        kwargs.setdefault("status", "active")  # new models default to active
        try:
            row = await self.repo.insert(**kwargs)
        except IntegrityError as exc:
            # fallbackId is a real FK now (unenforced in the old Mongo
            # repo) — a dangling reference fails loudly instead of being
            # silently stored.
            raise ValidationError("fallbackId does not reference an existing model") from exc
        return _to_schema(row)

    async def update(self, item_id: str, patch: AdminModelUpdate) -> AdminModel:
        # `exclude_unset=True` so only fields the client explicitly sent
        # get persisted — preserves untouched values.
        kwargs = _to_orm_kwargs(patch.model_dump(exclude_unset=True))
        try:
            row = await self.repo.update_by_id(item_id, **kwargs)
        except IntegrityError as exc:
            raise ValidationError("fallbackId does not reference an existing model") from exc
        if row is None:
            raise NotFoundError(f"Model {item_id} not found")
        return _to_schema(row)

    async def toggle_status(self, item_id: str) -> AdminModel:
        """Flip status between 'active' and 'inactive'."""
        current = await self.get(item_id)
        new_status = "inactive" if current.status == "active" else "active"
        return await self.update(item_id, AdminModelUpdate(status=new_status))

    async def delete(self, item_id: str) -> None:
        removed = await self.repo.delete_by_id(item_id)
        if not removed:
            raise NotFoundError(f"Model {item_id} not found")
