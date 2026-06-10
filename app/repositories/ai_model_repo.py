"""Repository for AI model configurations."""

from app.repositories.base import MongoRepository
from app.schemas.ai_model import AdminModel


class AIModelRepository(MongoRepository[AdminModel]):
    collection_name = "ai_models"
    read_model = AdminModel
