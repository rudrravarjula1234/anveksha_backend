"""Repository for bots (Postgres)."""

from app.models.bot import Bot
from app.repositories.sql_base import SqlRepository


class BotRepository(SqlRepository[Bot]):
    model = Bot
