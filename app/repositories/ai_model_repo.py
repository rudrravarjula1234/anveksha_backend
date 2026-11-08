"""Repository for AI model configurations (Postgres)."""

from app.models.ai_model import AIModel
from app.repositories.sql_base import SqlRepository


class AIModelRepository(SqlRepository[AIModel]):
    model = AIModel
