"""HTTP layer for `/api/admin/assessments-full` and `/api/admin/assessments`.

Both views are backed by the same `assessments` collection — the slim
variant is a projection. Response conventions match the mocks:

  -full:  POST → created item · PATCH → updated item ·
          toggle-publish → {ok: true} · DELETE → {ok: true}
  slim:   POST → created item (slim) · toggle-publish → {ok: true} ·
          DELETE → {ok: true}
"""

from fastapi import APIRouter, Depends

from app.auth.deps import require_roles
from app.schemas.assessment import (
    AdminAssessment,
    AssessmentFull,
    AssessmentFullCreate,
    AssessmentFullUpdate,
)
from app.services.assessment_service import AssessmentService

router_full = APIRouter(
    tags=["Admin · Assessments (full)"],
    dependencies=[Depends(require_roles("admin"))],
)
router_slim = APIRouter(
    tags=["Admin · Assessments"],
    dependencies=[Depends(require_roles("admin"))],
)


def _service() -> AssessmentService:
    return AssessmentService()


# ─── Full variant ────────────────────────────────────────────────────────

@router_full.get("", response_model=list[AssessmentFull])
async def list_full(service: AssessmentService = Depends(_service)) -> list[AssessmentFull]:
    return await service.list_full()


@router_full.post("", response_model=AssessmentFull)
async def create_full(
    payload: AssessmentFullCreate,
    service: AssessmentService = Depends(_service),
) -> AssessmentFull:
    return await service.create(payload)


@router_full.patch("/{item_id}", response_model=AssessmentFull)
async def update_full(
    item_id: str,
    patch: AssessmentFullUpdate,
    service: AssessmentService = Depends(_service),
) -> AssessmentFull:
    return await service.update(item_id, patch)


@router_full.post("/{item_id}/toggle-publish")
async def toggle_publish_full(
    item_id: str,
    service: AssessmentService = Depends(_service),
) -> dict[str, bool]:
    await service.toggle_publish(item_id)
    return {"ok": True}


@router_full.delete("/{item_id}")
async def delete_full(
    item_id: str,
    service: AssessmentService = Depends(_service),
) -> dict[str, bool]:
    await service.delete(item_id)
    return {"ok": True}


# ─── Slim variant ────────────────────────────────────────────────────────

@router_slim.get("", response_model=list[AdminAssessment])
async def list_slim(service: AssessmentService = Depends(_service)) -> list[AdminAssessment]:
    return await service.list_admin()


@router_slim.post("", response_model=AdminAssessment)
async def create_slim(
    payload: AssessmentFullCreate,
    service: AssessmentService = Depends(_service),
) -> AdminAssessment:
    created = await service.create(payload)
    return AdminAssessment.model_validate(created.model_dump())


@router_slim.post("/{item_id}/toggle-publish")
async def toggle_publish_slim(
    item_id: str,
    service: AssessmentService = Depends(_service),
) -> dict[str, bool]:
    await service.toggle_publish(item_id)
    return {"ok": True}


@router_slim.delete("/{item_id}")
async def delete_slim(
    item_id: str,
    service: AssessmentService = Depends(_service),
) -> dict[str, bool]:
    await service.delete(item_id)
    return {"ok": True}
