"""Index creation invoked once on app startup.

Idempotent — Mongo's `create_index` is a no-op when the same index
already exists. Adding a new index here ships with the next deploy.
"""

import logging

from app.db.mongo import get_database

log = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    db = get_database()

    # Models — `id` is our app-level id (ULID-prefixed), distinct from Mongo `_id`.
    await db.ai_models.create_index("id", unique=True)
    await db.ai_models.create_index("model")  # frequently queried
    await db.ai_models.create_index("status")

    # Bots
    await db.bots.create_index("id", unique=True)
    await db.bots.create_index("primaryModelId")
    await db.bots.create_index("status")
    await db.bots.create_index("specializations")  # multikey

    log.info("Mongo indexes ensured.")
