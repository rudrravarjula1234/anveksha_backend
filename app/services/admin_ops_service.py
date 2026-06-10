"""Admin ops business logic.

Mutations persist to Mongo so the admin console behaves like a real
backend (the mocks only mutated module-level arrays). Reads mirror the
mock envelopes exactly.

Collections:
- singletons keyed `{"key": "default"}`: admin_dashboard, admin_overview,
  integrity_signals, admin_analytics, admin_flag_registry, admin_flag_state
- per-document: admin_users, bots_simple, admin_feature_flags,
  admin_role_permissions, admin_dossiers, admin_slots, admin_verifiers,
  admin_candidates, admin_companies, integrity_flags, rbac_roles,
  rbac_custom_roles, rbac_audit, pilot_programs, pilot_students
"""

from datetime import datetime, timezone
from typing import Any

from ulid import ULID

from app.core.exceptions import NotFoundError
from app.db.mongo import get_database
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
    FlagsEnvelope,
    IntegrityEnvelope,
    PilotProgram,
    PilotProgramCreate,
    PilotProgramSimple,
    PilotStudent,
    PilotStudentCreate,
    RbacEnvelope,
    RolePermission,
    VerifierInviteRequest,
)


def _strip(doc: dict[str, Any]) -> dict[str, Any]:
    """Drop the Mongo internal id. Unlike the verifier module we keep
    `key` — for feature flags it's a contract field, and singletons pop
    their `key: "default"` marker in `_singleton` instead."""
    doc.pop("_id", None)
    return doc


def _new_id(prefix: str) -> str:
    return f"{prefix}_{str(ULID()).lower()}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdminOpsService:
    def _db(self):
        return get_database()

    async def _singleton(self, coll: str) -> dict[str, Any]:
        doc = await self._db()[coll].find_one({"key": "default"})
        if doc is None:
            raise RuntimeError(f"{coll} seed data missing")
        doc.pop("key", None)
        return _strip(doc)

    async def _list(self, coll: str, length: int = 500) -> list[dict[str, Any]]:
        docs = await self._db()[coll].find().to_list(length=length)
        return [_strip(d) for d in docs]

    # ── Dashboard / overview / analytics ────────────────────────────────

    async def dashboard(self) -> AdminDashboard:
        return AdminDashboard.model_validate(await self._singleton("admin_dashboard"))

    async def overview(self) -> AdminOverview:
        return AdminOverview.model_validate(await self._singleton("admin_overview"))

    async def analytics(self) -> AnalyticsData:
        return AnalyticsData.model_validate(await self._singleton("admin_analytics"))

    # ── Users ────────────────────────────────────────────────────────────

    async def users(self) -> list[AdminUser]:
        return [AdminUser.model_validate(d) for d in await self._list("admin_users")]

    async def _propagate_user_update(self, user_id: str, diff: dict[str, Any]) -> None:
        """Best-effort sync into the auth `users` collection so role/active
        changes actually affect login — no-op when the id isn't seeded there."""
        await self._db()["users"].find_one_and_update({"id": user_id}, {"$set": diff})

    async def update_user_roles(self, user_id: str, roles: list[str]) -> dict[str, Any]:
        updated = await self._db()["admin_users"].find_one_and_update(
            {"id": user_id}, {"$set": {"roles": roles}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"User {user_id} not found")
        await self._propagate_user_update(user_id, {"roles": roles})
        return {"ok": True, "userId": user_id, "roles": roles}

    async def deactivate_user(self, user_id: str) -> dict[str, Any]:
        updated = await self._db()["admin_users"].find_one_and_update(
            {"id": user_id}, {"$set": {"is_active": False}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"User {user_id} not found")
        await self._propagate_user_update(user_id, {"is_active": False})
        return {"ok": True, "userId": user_id}

    # ── Bots (simple shape — /api/bots) ──────────────────────────────────

    async def simple_bots(self) -> list[Bot]:
        return [Bot.model_validate(d) for d in await self._list("bots_simple")]

    async def create_simple_bot(self, payload: BotCreate) -> Bot:
        doc = {
            "id": _new_id("bot"),
            "name": payload.name or "New Bot",
            "description": payload.description or "",
            "type": payload.type or "interviewer",
            "model": payload.model or "claude-opus-4-7",
            "status": "draft",
            "sessionsRun": 0,
            "avgRating": 0,
            "createdAt": _now_iso(),
        }
        await self._db()["bots_simple"].insert_one(doc)
        return Bot.model_validate(_strip(doc))

    # ── Feature flags (simple list — /api/admin/feature-flags) ──────────

    async def feature_flags(self) -> list[FeatureFlag]:
        return [FeatureFlag.model_validate(d) for d in await self._list("admin_feature_flags")]

    async def update_feature_flag(self, key: str, enabled: bool) -> FeatureFlag:
        updated = await self._db()["admin_feature_flags"].find_one_and_update(
            {"key": key}, {"$set": {"enabled": enabled}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"Feature flag {key} not found")
        return FeatureFlag.model_validate(_strip(updated))

    # ── Role permissions (simple list — /api/admin/permissions) ─────────

    async def permissions(self) -> list[RolePermission]:
        return [RolePermission.model_validate(d) for d in await self._list("admin_role_permissions")]

    # ── Dossiers ─────────────────────────────────────────────────────────

    async def dossiers(self) -> list[AdminDossier]:
        return [AdminDossier.model_validate(d) for d in await self._list("admin_dossiers")]

    async def create_dossier(self, payload: DossierCreate) -> AdminDossier:
        doc = {
            "id": _new_id("svr"),
            "candidate": payload.candidate or "",
            "skill": payload.skill or "",
            "verifier": payload.verifier or "",
            "date": payload.date or datetime.now(timezone.utc).strftime("%b %d"),
            "score": payload.score or 0,
            "status": payload.status or "draft",
        }
        await self._db()["admin_dossiers"].insert_one(doc)
        return AdminDossier.model_validate(_strip(doc))

    async def patch_dossier(self, dossier_id: str, patch: DossierPatch) -> AdminDossier:
        diff = patch.model_dump(exclude_unset=True)
        coll = self._db()["admin_dossiers"]
        if diff:
            updated = await coll.find_one_and_update(
                {"id": dossier_id}, {"$set": diff}, return_document=True
            )
        else:
            updated = await coll.find_one({"id": dossier_id})
        if updated is None:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        return AdminDossier.model_validate(_strip(updated))

    async def publish_dossier(self, dossier_id: str) -> dict[str, Any]:
        updated = await self._db()["admin_dossiers"].find_one_and_update(
            {"id": dossier_id}, {"$set": {"status": "published"}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        return {"ok": True}

    async def delete_dossier(self, dossier_id: str) -> dict[str, Any]:
        result = await self._db()["admin_dossiers"].delete_one({"id": dossier_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        return {"ok": True}

    # ── Slots (admin view) ───────────────────────────────────────────────

    async def slots(self) -> list[AdminSlot]:
        return [AdminSlot.model_validate(d) for d in await self._list("admin_slots")]

    async def create_slot(self, payload: AdminSlotCreate) -> AdminSlot:
        doc = {
            "id": _new_id("slt"),
            "verifier": payload.verifier or "Unassigned",
            "day": payload.day or "",
            "time": payload.time or "",
            "duration": payload.duration or 60,
            "skill": payload.skill or "Any",
            "booked": False,
        }
        await self._db()["admin_slots"].insert_one(doc)
        return AdminSlot.model_validate(_strip(doc))

    async def block_slot(self, slot_id: str) -> dict[str, Any]:
        """Mock parity: blocking removes the slot from the pool."""
        result = await self._db()["admin_slots"].delete_one({"id": slot_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Slot {slot_id} not found")
        return {"ok": True}

    # ── Verifiers (admin roster) ─────────────────────────────────────────

    async def verifiers(self) -> list[AdminVerifier]:
        return [AdminVerifier.model_validate(d) for d in await self._list("admin_verifiers")]

    async def invite_verifier(self, payload: VerifierInviteRequest) -> dict[str, Any]:
        # Mock parity: the invite is acknowledged but creates no roster row.
        return {"ok": True, "email": payload.email, "specialization": payload.specialization}

    async def approve_verifier(self, verifier_id: str) -> dict[str, Any]:
        updated = await self._db()["admin_verifiers"].find_one_and_update(
            {"id": verifier_id},
            {"$set": {"tier": "active", "since": "Apr 2026"}},
            return_document=True,
        )
        if updated is None:
            raise NotFoundError(f"Verifier {verifier_id} not found")
        return {"ok": True}

    async def suspend_verifier(self, verifier_id: str) -> dict[str, Any]:
        updated = await self._db()["admin_verifiers"].find_one_and_update(
            {"id": verifier_id}, {"$set": {"tier": "probation"}}, return_document=True
        )
        if updated is None:
            raise NotFoundError(f"Verifier {verifier_id} not found")
        return {"ok": True}

    # ── Candidates / companies (admin views) ─────────────────────────────

    async def candidates(self) -> list[AdminCandidate]:
        return [AdminCandidate.model_validate(d) for d in await self._list("admin_candidates")]

    async def companies(self) -> list[AdminCompany]:
        return [AdminCompany.model_validate(d) for d in await self._list("admin_companies")]

    async def impersonate_company(self, company_id: str) -> dict[str, Any]:
        company = await self._db()["admin_companies"].find_one({"id": company_id})
        if company is None:
            raise NotFoundError(f"Company {company_id} not found")
        return {"ok": True, "sessionId": _new_id("imp"), "companyId": company_id}

    # ── Integrity ────────────────────────────────────────────────────────

    async def integrity(self) -> IntegrityEnvelope:
        flags = await self._list("integrity_flags")
        signals = (await self._singleton("integrity_signals")).get("signals", [])
        return IntegrityEnvelope.model_validate({"flags": flags, "signals": signals})

    async def resolve_integrity_flag(self, flag_id: str, action: str | None) -> dict[str, Any]:
        updated = await self._db()["integrity_flags"].find_one_and_update(
            {"id": flag_id},
            {"$set": {"severity": "confirmed", "action": action or "Resolved"}},
            return_document=True,
        )
        if updated is None:
            raise NotFoundError(f"Integrity flag {flag_id} not found")
        return {"ok": True}

    # ── Feature flags (rich registry + state — /api/admin/flags) ────────

    async def _flag_registry(self) -> list[dict[str, Any]]:
        return (await self._singleton("admin_flag_registry")).get("registry", [])

    async def _flag_state(self) -> dict[str, bool]:
        return dict((await self._singleton("admin_flag_state")).get("state", {}))

    async def _set_flag_state(self, state: dict[str, bool]) -> None:
        await self._db()["admin_flag_state"].find_one_and_update(
            {"key": "default"}, {"$set": {"state": state}}, return_document=True
        )

    async def flags(self) -> FlagsEnvelope:
        return FlagsEnvelope.model_validate(
            {"registry": await self._flag_registry(), "state": await self._flag_state()}
        )

    async def update_flags(self, patch: dict[str, bool]) -> dict[str, Any]:
        state = await self._flag_state()
        state.update(patch)
        await self._set_flag_state(state)
        return {"ok": True, "state": state}

    async def reset_flags(self) -> dict[str, Any]:
        state: dict[str, bool] = {}
        for group in await self._flag_registry():
            for flag in group.get("flags", []):
                state[flag["id"]] = flag["default"]
        await self._set_flag_state(state)
        return {"ok": True, "state": state}

    async def toggle_flag_group(self, group_name: str, value: bool) -> dict[str, Any]:
        state = await self._flag_state()
        for group in await self._flag_registry():
            if group.get("group") == group_name:
                for flag in group.get("flags", []):
                    state[flag["id"]] = value
        # Mock parity: unknown groups are a no-op that still returns ok+state.
        await self._set_flag_state(state)
        return {"ok": True, "state": state}

    # ── RBAC ─────────────────────────────────────────────────────────────

    async def rbac(self) -> RbacEnvelope:
        return RbacEnvelope.model_validate(
            {
                "roles": await self._list("rbac_roles"),
                "customRoles": await self._list("rbac_custom_roles"),
                "audit": await self._list("rbac_audit"),
            }
        )

    async def set_role_permission(self, role_id: str, perm_id: str, on: bool) -> dict[str, Any]:
        coll = self._db()["rbac_roles"]
        role = await coll.find_one({"id": role_id})
        if role is None:
            raise NotFoundError(f"Role {role_id} not found")
        # Locked permissions never flip; unknown perm ids are a no-op
        # (mock parity — the handler still answers {ok: true}).
        perms = [
            {**p, "on": on} if p.get("id") == perm_id and not p.get("locked") else p
            for p in role.get("perms", [])
        ]
        await coll.find_one_and_update({"id": role_id}, {"$set": {"perms": perms}})
        return {"ok": True}

    async def create_custom_role(self, payload: CustomRoleCreate) -> CustomRole:
        doc = {
            "id": _new_id("cr"),
            "name": payload.name or "New role",
            "baseRole": payload.baseRole or "candidate",
            "desc": payload.desc or "",
            "members": 0,
            "overrides": payload.overrides or {},
        }
        await self._db()["rbac_custom_roles"].insert_one(doc)
        return CustomRole.model_validate(_strip(doc))

    async def delete_custom_role(self, role_id: str) -> dict[str, Any]:
        result = await self._db()["rbac_custom_roles"].delete_one({"id": role_id})
        if result.deleted_count != 1:
            raise NotFoundError(f"Custom role {role_id} not found")
        return {"ok": True}

    # ── Pilots ───────────────────────────────────────────────────────────

    async def pilots_simple(self) -> list[PilotProgramSimple]:
        # Same collection as pilots-full; the simple schema projects away
        # dept/assessments (ReadModel ignores extras).
        return [PilotProgramSimple.model_validate(d) for d in await self._list("pilot_programs")]

    async def pilots_full(self) -> list[PilotProgram]:
        return [PilotProgram.model_validate(d) for d in await self._list("pilot_programs")]

    async def create_pilot(self, payload: PilotProgramCreate) -> PilotProgram:
        doc = {
            "id": _new_id("plt"),
            "name": payload.name or "New pilot",
            "college": payload.college or "",
            "dept": payload.dept or "Computer Science",
            "batch": payload.batch or "2024-25",
            "coordinator": payload.coordinator or "",
            "status": "draft",
            "students": 0,
            "completed": 0,
            "avgScore": 0,
            "startDate": payload.startDate or "",
            "endDate": payload.endDate or "",
            "assessments": payload.assessments or [],
        }
        await self._db()["pilot_programs"].insert_one(doc)
        return PilotProgram.model_validate(_strip(doc))

    # ── Pilot students ───────────────────────────────────────────────────

    async def pilot_students(self) -> list[PilotStudent]:
        return [PilotStudent.model_validate(d) for d in await self._list("pilot_students")]

    async def _bump_program_students(self, counts: dict[str, int]) -> None:
        """Increment each program's `students` count. Unknown program ids
        are skipped (mock parity — the student row is still created)."""
        coll = self._db()["pilot_programs"]
        for program_id, n in counts.items():
            program = await coll.find_one({"id": program_id})
            if program is not None:
                await coll.find_one_and_update(
                    {"id": program_id},
                    {"$set": {"students": program.get("students", 0) + n}},
                )

    def _new_student_doc(self, row: PilotStudentCreate) -> dict[str, Any]:
        return {
            "id": _new_id("stu"),
            "name": row.name,
            "email": row.email,
            "program": row.program,
            "completed": 0,
            "pending": 3,
            "avgScore": 0,
            "status": "registered",
        }

    async def create_pilot_student(self, payload: PilotStudentCreate) -> PilotStudent:
        doc = self._new_student_doc(payload)
        await self._db()["pilot_students"].insert_one(doc)
        await self._bump_program_students({payload.program: 1})
        return PilotStudent.model_validate(_strip(doc))

    async def import_pilot_students(self, rows: list[PilotStudentCreate]) -> dict[str, Any]:
        coll = self._db()["pilot_students"]
        counts: dict[str, int] = {}
        for row in rows:
            await coll.insert_one(self._new_student_doc(row))
            counts[row.program] = counts.get(row.program, 0) + 1
        await self._bump_program_students(counts)
        return {"ok": True, "count": len(rows)}
