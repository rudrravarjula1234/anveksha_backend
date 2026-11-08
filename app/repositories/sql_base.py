"""Generic SQLAlchemy CRUD base. Concrete repositories subclass
`SqlRepository[ModelT]` and set `model`. Returns ORM instances, not API
schemas — mapping to the Pydantic contract is the service layer's job.
"""

from typing import Any, ClassVar, Generic, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class SqlRepository(Generic[ModelT]):
    model: ClassVar[Type[Any]]

    def __init__(self, db: AsyncSession) -> None:
        assert self.model is not None, "Subclasses must set `model`"
        self.db = db

    async def insert(self, **fields: Any) -> ModelT:
        """Insert a new row. Caller must populate `id` and any
        domain-required fields; `created_at`/`updated_at` are stamped by
        the DB (`TimestampMixin`'s `server_default`)."""
        instance = self.model(**fields)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def find_by_id(self, item_id: str) -> Optional[ModelT]:
        return await self.db.get(self.model, item_id)

    async def list_all(self, *, limit: int = 500) -> list[ModelT]:
        # `id` tiebreaker: ORDER BY created_at alone is non-deterministic
        # when rows share a timestamp (day-granularity seed data).
        stmt = (
            select(self.model)
            .order_by(self.model.created_at.desc(), self.model.id)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_by_id(self, item_id: str, **patch: Any) -> Optional[ModelT]:
        """Apply a non-empty patch and return the updated row.

        Returns None if no row matches (the service layer maps that to
        404). Empty patches short-circuit to a plain read.
        """
        instance = await self.db.get(self.model, item_id)
        if instance is None:
            return None
        for key, value in patch.items():
            setattr(instance, key, value)
        if patch:
            await self.db.flush()
            await self.db.refresh(instance)
        return instance

    async def delete_by_id(self, item_id: str) -> bool:
        instance = await self.db.get(self.model, item_id)
        if instance is None:
            return False
        await self.db.delete(instance)
        await self.db.flush()
        return True
