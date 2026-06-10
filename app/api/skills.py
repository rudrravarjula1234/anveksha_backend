"""HTTP layer for `/api/skills`.

Contract mirror of `anveksha_ui/src/mocks/handlers/skills.ts`:

    GET /api/skills/ledger — bearer-aware composite ledger
    GET /api/skills        — just the rows (ledger.skills)
"""

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, get_current_principal
from app.schemas.skill import SkillLedger, SkillLedgerRow
from app.services.skill_service import SkillService

router = APIRouter(tags=["Skills"])


def _service() -> SkillService:
    return SkillService()


@router.get("/ledger", response_model=SkillLedger)
async def get_ledger(
    principal: Principal = Depends(get_current_principal),
    service: SkillService = Depends(_service),
) -> SkillLedger:
    return await service.ledger_for_user(principal.user_id)


@router.get("", response_model=list[SkillLedgerRow])
async def get_skills(
    principal: Principal = Depends(get_current_principal),
    service: SkillService = Depends(_service),
) -> list[SkillLedgerRow]:
    ledger = await service.ledger_for_user(principal.user_id)
    return ledger.skills
