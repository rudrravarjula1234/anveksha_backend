"""HTTP layer for the admin platform dashboard.

`GET /api/admin/metrics/platform` — a single admin-only read returning
platform-wide counts (agents, bots, models, users), LLM token consumption,
and Temporal workflow stats. Mounted at prefix="/api/admin/metrics".
"""

from fastapi import APIRouter, Depends

from app.auth.deps import require_roles
from app.schemas.admin_metrics import PlatformMetrics
from app.services.platform_metrics_service import PlatformMetricsService

router = APIRouter(
    tags=["Admin · Metrics"],
    dependencies=[Depends(require_roles("admin"))],
)


def _service() -> PlatformMetricsService:
    return PlatformMetricsService()


@router.get("/platform", response_model=PlatformMetrics)
async def platform_metrics(
    service: PlatformMetricsService = Depends(_service),
) -> PlatformMetrics:
    return await service.metrics()
