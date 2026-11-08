"""HTTP layer for `/api/admin/models`.

Routes match the frontend mock contract one-to-one:

    GET    /api/admin/models           — list
    POST   /api/admin/models           — create
    PATCH  /api/admin/models/{id}      — partial update
    POST   /api/admin/models/{id}/toggle — flip active/inactive
    DELETE /api/admin/models/{id}      — remove

Every route requires the admin role. Mounting prefix lives in
`app.main`.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_roles
from app.db.session import get_session
from app.schemas.ai_model import AdminModel, AdminModelCreate, AdminModelUpdate
from app.services.ai_model_service import AIModelService

router = APIRouter(
    tags=["Admin · Models"],
    dependencies=[Depends(require_roles("admin"))],
)


def _service(db: AsyncSession = Depends(get_session)) -> AIModelService:
    return AIModelService(db)


@router.get("", response_model=list[AdminModel])
async def list_models(service: AIModelService = Depends(_service)) -> list[AdminModel]:
    return await service.list_models()


@router.post("", response_model=AdminModel, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: AdminModelCreate,
    service: AIModelService = Depends(_service),
) -> AdminModel:
    return await service.create(payload)


@router.patch("/{model_id}", response_model=AdminModel)
async def update_model(
    model_id: str,
    patch: AdminModelUpdate,
    service: AIModelService = Depends(_service),
) -> AdminModel:
    return await service.update(model_id, patch)


@router.post("/{model_id}/toggle", response_model=AdminModel)
async def toggle_model(
    model_id: str,
    service: AIModelService = Depends(_service),
) -> AdminModel:
    return await service.toggle_status(model_id)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: str,
    service: AIModelService = Depends(_service),
) -> None:
    await service.delete(model_id)
