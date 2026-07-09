"""Motor (async PyMongo) client lifecycle.

A single AsyncIOMotorClient is created at app startup and closed on
shutdown. Repositories pick up the live database handle via
`get_database()`.
"""

import logging
from typing import Optional
from urllib.parse import urlsplit

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

log = logging.getLogger(__name__)


class _MongoState:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


_state = _MongoState()


async def connect_to_mongo() -> None:
    """Open the connection pool and verify reachability via `ping`.

    Called from the FastAPI lifespan handler in `app.main`. Surfaces
    connection errors loudly at startup so the API doesn't accept
    traffic against an unreachable DB.
    """
    if _state.client is not None:
        return

    settings = get_settings()
    # Log the REAL target host (parsed from the resolved URI) so cloud vs
    # local is obvious — MONGO_HOST is meaningless when MONGO_URI/MONGODB_URI
    # is set. Credentials are never part of the parsed hostname.
    target_host = urlsplit(settings.mongo_connection_uri).hostname or settings.MONGO_HOST
    log.info("Connecting to MongoDB at %s/%s", target_host, settings.MONGO_DATABASE)

    _state.client = AsyncIOMotorClient(
        settings.mongo_connection_uri,
        serverSelectionTimeoutMS=5_000,
        uuidRepresentation="standard",
    )
    _state.db = _state.client[settings.MONGO_DATABASE]

    # Fail fast on bad credentials / unreachable host.
    await _state.client.admin.command("ping")
    log.info("MongoDB connection established.")


async def close_mongo() -> None:
    if _state.client is not None:
        _state.client.close()
        log.info("MongoDB connection closed.")
    _state.client = None
    _state.db = None


def get_database() -> AsyncIOMotorDatabase:
    """Return the active database handle.

    Raises if the connection hasn't been initialised — should never
    happen in normal runtime because `connect_to_mongo()` runs in the
    lifespan handler before requests are accepted.
    """
    if _state.db is None:
        raise RuntimeError("Mongo not initialised — call connect_to_mongo() first.")
    return _state.db
