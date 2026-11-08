"""HTTP layer for the admin ops console.

Two routers:

- `router` — every `/api/admin/*` path from the admin mock handlers
  (dashboard, users, feature flags, permissions, overview, dossiers,
  slots, verifiers, candidates, companies, integrity, analytics, rich
  flags, RBAC, pilots, pilot students). Paths are fully qualified, so
  mount at prefix="/api/admin". Admin-only.
- `bots_simple_router` — the SIMPLE bot list from `src/types/admin.ts`
  (NOT the BotFull registry at /api/admin/bots). Mount at
  prefix="/api/bots". The mock has no role gate, so any authenticated
  principal may call it.

Contract mirror of `anveksha_ui/src/mocks/handlers/admin.ts`,
`adminWorkflow.ts`, and the flags/rbac/pilots slices of `adminRich.ts`.
"""

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_principal, require_roles
from app.db.session import get_session
from app.schemas.admin_ops import (
    AdminCandidate,
    AdminCompany,
    AdminDashboard,
    AdminDossier,
    AdminOverview,
    AdminSlot,
    AdminSlotCreate,
    AdminUser,
    AdminVerifier,
    AnalyticsData,
    Bot,
    BotCreate,
    CustomRole,
    CustomRoleCreate,
    DossierCreate,
    DossierPatch,
    FeatureFlag,
    FeatureFlagUpdate,
    FlagGroupToggle,
    FlagsEnvelope,
    FlagsStateResponse,
    IntegrityEnvelope,
    PilotProgram,
    PilotProgramCreate,
    PilotProgramSimple,
    PilotStudent,
    PilotStudentCreate,
    PilotStudentImportRequest,
    RbacEnvelope,
    RbacPermUpdate,
    RolePermission,
    UserRolesUpdate,
    VerifierInviteRequest,
)
from app.services.admin_ops_service import AdminOpsService

router = APIRouter(
    tags=["Admin · Ops"],
    dependencies=[Depends(require_roles("admin"))],
)

bots_simple_router = APIRouter(
    tags=["Bots (simple)"],
    dependencies=[Depends(get_current_principal)],
)


def _service(db: AsyncSession = Depends(get_session)) -> AdminOpsService:
    return AdminOpsService(db)


# ─── Dashboard / overview / analytics ────────────────────────────────────


@router.get("/dashboard", response_model=AdminDashboard)
async def dashboard(service: AdminOpsService = Depends(_service)) -> AdminDashboard:
    return await service.dashboard()


@router.get("/overview", response_model=AdminOverview)
async def overview(service: AdminOpsService = Depends(_service)) -> AdminOverview:
    return await service.overview()


@router.get("/analytics", response_model=AnalyticsData)
async def analytics(service: AdminOpsService = Depends(_service)) -> AnalyticsData:
    return await service.analytics()


# ─── Users ───────────────────────────────────────────────────────────────


@router.get("/users", response_model=list[AdminUser])
async def list_users(service: AdminOpsService = Depends(_service)) -> list[AdminUser]:
    return await service.users()


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    payload: UserRolesUpdate,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.update_user_roles(user_id, list(payload.roles))


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.deactivate_user(user_id)


# ─── Feature flags (simple list) ─────────────────────────────────────────


@router.get("/feature-flags", response_model=list[FeatureFlag])
async def list_feature_flags(
    service: AdminOpsService = Depends(_service),
) -> list[FeatureFlag]:
    return await service.feature_flags()


@router.put("/feature-flags/{key}", response_model=FeatureFlag)
async def update_feature_flag(
    key: str,
    payload: FeatureFlagUpdate,
    service: AdminOpsService = Depends(_service),
) -> FeatureFlag:
    return await service.update_feature_flag(key, payload.enabled)


# ─── Role permissions (simple list) ──────────────────────────────────────


@router.get("/permissions", response_model=list[RolePermission])
async def list_permissions(
    service: AdminOpsService = Depends(_service),
) -> list[RolePermission]:
    return await service.permissions()


# ─── Dossiers ────────────────────────────────────────────────────────────


@router.get("/dossiers", response_model=list[AdminDossier])
async def list_dossiers(service: AdminOpsService = Depends(_service)) -> list[AdminDossier]:
    return await service.dossiers()


@router.post("/dossiers", response_model=AdminDossier)
async def create_dossier(
    payload: DossierCreate,
    service: AdminOpsService = Depends(_service),
) -> AdminDossier:
    return await service.create_dossier(payload)


@router.patch("/dossiers/{dossier_id}", response_model=AdminDossier)
async def patch_dossier(
    dossier_id: str,
    patch: DossierPatch,
    service: AdminOpsService = Depends(_service),
) -> AdminDossier:
    return await service.patch_dossier(dossier_id, patch)


@router.post("/dossiers/{dossier_id}/publish")
async def publish_dossier(
    dossier_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.publish_dossier(dossier_id)


@router.delete("/dossiers/{dossier_id}")
async def delete_dossier(
    dossier_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.delete_dossier(dossier_id)


# ─── Slots ───────────────────────────────────────────────────────────────


@router.get("/slots", response_model=list[AdminSlot])
async def list_slots(service: AdminOpsService = Depends(_service)) -> list[AdminSlot]:
    return await service.slots()


@router.post("/slots", response_model=AdminSlot)
async def create_slot(
    payload: AdminSlotCreate,
    service: AdminOpsService = Depends(_service),
) -> AdminSlot:
    return await service.create_slot(payload)


@router.post("/slots/{slot_id}/block")
async def block_slot(
    slot_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.block_slot(slot_id)


# ─── Verifiers ───────────────────────────────────────────────────────────


@router.get("/verifiers", response_model=list[AdminVerifier])
async def list_verifiers(
    service: AdminOpsService = Depends(_service),
) -> list[AdminVerifier]:
    return await service.verifiers()


@router.post("/verifiers/invite")
async def invite_verifier(
    payload: VerifierInviteRequest,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.invite_verifier(payload)


@router.post("/verifiers/{verifier_id}/approve")
async def approve_verifier(
    verifier_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.approve_verifier(verifier_id)


@router.post("/verifiers/{verifier_id}/suspend")
async def suspend_verifier(
    verifier_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.suspend_verifier(verifier_id)


# ─── Candidates / companies ──────────────────────────────────────────────


@router.get("/candidates", response_model=list[AdminCandidate])
async def list_candidates(
    service: AdminOpsService = Depends(_service),
) -> list[AdminCandidate]:
    return await service.candidates()


@router.get("/companies", response_model=list[AdminCompany])
async def list_companies(
    service: AdminOpsService = Depends(_service),
) -> list[AdminCompany]:
    return await service.companies()


@router.post("/companies/{company_id}/impersonate")
async def impersonate_company(
    company_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.impersonate_company(company_id)


# ─── Integrity ───────────────────────────────────────────────────────────


@router.get("/integrity", response_model=IntegrityEnvelope)
async def integrity(service: AdminOpsService = Depends(_service)) -> IntegrityEnvelope:
    return await service.integrity()


@router.post("/integrity/{flag_id}/resolve")
async def resolve_integrity_flag(
    flag_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    # The mock tolerates a missing/partial body and reads only `action`.
    action = body.get("action")
    return await service.resolve_integrity_flag(
        flag_id, action if isinstance(action, str) else None
    )


# ─── Feature flags (rich registry + state) ───────────────────────────────


@router.get("/flags", response_model=FlagsEnvelope)
async def flags(service: AdminOpsService = Depends(_service)) -> FlagsEnvelope:
    return await service.flags()


@router.put("/flags", response_model=FlagsStateResponse)
async def update_flags(
    patch: dict[str, bool] = Body(default_factory=dict),
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.update_flags(patch)


@router.post("/flags/reset", response_model=FlagsStateResponse)
async def reset_flags(service: AdminOpsService = Depends(_service)) -> dict[str, Any]:
    return await service.reset_flags()


@router.post("/flags/group/{group}", response_model=FlagsStateResponse)
async def toggle_flag_group(
    group: str,
    payload: FlagGroupToggle,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.toggle_flag_group(group, payload.value)


# ─── RBAC ────────────────────────────────────────────────────────────────


@router.get("/rbac", response_model=RbacEnvelope)
async def rbac(service: AdminOpsService = Depends(_service)) -> RbacEnvelope:
    return await service.rbac()


@router.put("/rbac/{role}/{perm}")
async def set_role_permission(
    role: str,
    perm: str,
    payload: RbacPermUpdate,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.set_role_permission(role, perm, payload.on)


@router.post("/rbac/custom", response_model=CustomRole)
async def create_custom_role(
    payload: CustomRoleCreate,
    service: AdminOpsService = Depends(_service),
) -> CustomRole:
    return await service.create_custom_role(payload)


@router.delete("/rbac/custom/{custom_id}")
async def delete_custom_role(
    custom_id: str,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.delete_custom_role(custom_id)


# ─── Pilots ──────────────────────────────────────────────────────────────


@router.get("/pilots", response_model=list[PilotProgramSimple])
async def list_pilots_simple(
    service: AdminOpsService = Depends(_service),
) -> list[PilotProgramSimple]:
    return await service.pilots_simple()


@router.get("/pilots-full", response_model=list[PilotProgram])
async def list_pilots_full(
    service: AdminOpsService = Depends(_service),
) -> list[PilotProgram]:
    return await service.pilots_full()


@router.post("/pilots-full", response_model=PilotProgram)
async def create_pilot(
    payload: PilotProgramCreate,
    service: AdminOpsService = Depends(_service),
) -> PilotProgram:
    return await service.create_pilot(payload)


# ─── Pilot students ──────────────────────────────────────────────────────


@router.get("/pilot-students", response_model=list[PilotStudent])
async def list_pilot_students(
    service: AdminOpsService = Depends(_service),
) -> list[PilotStudent]:
    return await service.pilot_students()


@router.post("/pilot-students", response_model=PilotStudent)
async def create_pilot_student(
    payload: PilotStudentCreate,
    service: AdminOpsService = Depends(_service),
) -> PilotStudent:
    return await service.create_pilot_student(payload)


@router.post("/pilot-students/import")
async def import_pilot_students(
    payload: PilotStudentImportRequest,
    service: AdminOpsService = Depends(_service),
) -> dict[str, Any]:
    return await service.import_pilot_students(payload.rows)


# ─── Bots — simple shape, mounted at /api/bots ───────────────────────────


@bots_simple_router.get("", response_model=list[Bot])
async def list_bots(service: AdminOpsService = Depends(_service)) -> list[Bot]:
    return await service.simple_bots()


@bots_simple_router.post("", response_model=Bot)
async def create_bot(
    payload: BotCreate,
    service: AdminOpsService = Depends(_service),
) -> Bot:
    return await service.create_simple_bot(payload)
