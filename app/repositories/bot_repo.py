"""Repository for bot configurations."""

from app.repositories.base import MongoRepository
from app.schemas.bot import BotFull


class BotRepository(MongoRepository[BotFull]):
    collection_name = "bots"
    read_model = BotFull
