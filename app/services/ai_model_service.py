"""Business logic for AI model configurations.

Thin today (it's mostly straight CRUD), but the indirection lets us
introduce things like uniqueness checks, audit logging, or cache
invalidation later without touching the API handlers.
"""

from typing import Optional

from app.core.exceptions import NotFoundError
from app.core.ids import model_id
from app.repositories.ai_model_repo import AIModelRepository
from app.schemas.ai_model import (
    AdminModel,
    AdminModelCreate,
    AdminModelUpdate,
)


class AIModelService:
    def __init__(self, repo: Optional[AIModelRepository] = None) -> None:
        self.repo = repo or AIModelRepository()

    async def list_models(self) -> list[AdminModel]:
        return await self.repo.list_all()

    async def get(self, item_id: str) -> AdminModel:
        item = await self.repo.find_by_id(item_id)
        if item is None:
            raise NotFoundError(f"Model {item_id} not found")
        return item

    async def create(self, payload: AdminModelCreate) -> AdminModel:
        doc = payload.model_dump()
        doc["id"] = model_id()
        doc.setdefault("status", "active")  # new models default to active
        return await self.repo.insert(doc)

    async def update(self, item_id: str, patch: AdminModelUpdate) -> AdminModel:
        # `exclude_unset=True` so only fields the client explicitly sent
        # get persisted — preserves untouched values.
        diff = patch.model_dump(exclude_unset=True)
        updated = await self.repo.update_by_id(item_id, diff)
        if updated is None:
            raise NotFoundError(f"Model {item_id} not found")
        return updated

    async def toggle_status(self, item_id: str) -> AdminModel:
        """Flip status between 'active' and 'inactive'."""
        current = await self.get(item_id)
        new_status = "inactive" if current.status == "active" else "active"
        return await self.update(item_id, AdminModelUpdate(status=new_status))

    async def delete(self, item_id: str) -> None:
        removed = await self.repo.delete_by_id(item_id)
        if not removed:
            raise NotFoundError(f"Model {item_id} not found")
