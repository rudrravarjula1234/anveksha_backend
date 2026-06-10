"""Generic Mongo CRUD base.

Concrete repositories subclass `MongoRepository[T]` and only supply the
collection name + the Pydantic read-model type. Everything else — find,
list, insert, update, delete — is provided.

Documents are stored with our app-level string `id` as the canonical
identifier (indexed in `app/db/indexes.py`). Mongo's `_id` is treated as
internal-only and stripped from reads via `_strip_oid`.
"""

from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, Optional, Type, TypeVar

from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel

from app.db.mongo import get_database

T = TypeVar("T", bound=BaseModel)


class MongoRepository(Generic[T]):
    collection_name: ClassVar[str] = ""
    read_model: ClassVar[Type[BaseModel]]

    def __init__(self) -> None:
        assert self.collection_name, "Subclasses must set collection_name"
        assert hasattr(self, "read_model"), "Subclasses must set read_model"

    # ── Internal helpers ────────────────────────────────────────────────

    def _coll(self) -> AsyncIOMotorCollection:
        return get_database()[self.collection_name]

    @staticmethod
    def _strip_oid(doc: dict[str, Any]) -> dict[str, Any]:
        """Remove Mongo's `_id` so the public shape is exactly our schema."""
        doc.pop("_id", None)
        return doc

    def _to_model(self, doc: Optional[dict[str, Any]]) -> Optional[T]:
        if doc is None:
            return None
        return self.read_model.model_validate(self._strip_oid(doc))  # type: ignore[return-value]

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    # ── CRUD ────────────────────────────────────────────────────────────

    async def insert(self, doc: dict[str, Any]) -> T:
        """Insert a new document. Caller must populate `id` and any
        domain-required fields. We stamp `createdAt` / `updatedAt`."""
        now = self._now()
        doc.setdefault("createdAt", now)
        doc["updatedAt"] = now
        await self._coll().insert_one(doc)
        return self._to_model(doc)  # type: ignore[return-value]

    async def find_by_id(self, item_id: str) -> Optional[T]:
        doc = await self._coll().find_one({"id": item_id})
        return self._to_model(doc)

    async def list_all(self, *, limit: int = 500) -> list[T]:
        cursor = self._coll().find().sort("createdAt", -1).limit(limit)
        items = await cursor.to_list(length=limit)
        return [self._to_model(d) for d in items if d is not None]  # type: ignore[misc]

    async def update_by_id(self, item_id: str, patch: dict[str, Any]) -> Optional[T]:
        """Apply a non-empty patch and return the updated doc.

        Returns None if no doc matches (the API layer maps that to 404).
        Empty patches short-circuit to a plain read.
        """
        if not patch:
            return await self.find_by_id(item_id)
        patch["updatedAt"] = self._now()
        updated = await self._coll().find_one_and_update(
            {"id": item_id},
            {"$set": patch},
            return_document=True,  # ReturnDocument.AFTER
        )
        return self._to_model(updated)

    async def delete_by_id(self, item_id: str) -> bool:
        result = await self._coll().delete_one({"id": item_id})
        return result.deleted_count == 1
