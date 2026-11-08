"""Admin ops business logic.

Collections:
- console snapshot: admin_console_snapshots (one row, `id = "singleton"`;
  merged from the former admin_dashboard/admin_overview/admin_analytics/
  integrity_signals singletons)
- feature flag registry+state: flag_groups, flag_defs, flag_state
- per-row: users (merged `admin_users`), bots (merged `bots_simple`),
  admin_feature_flags, admin_role_permissions, admin_dossiers,
  admin_slots, admin_verifiers, admin_candidates, admin_companies,
  integrity_flags, rbac_roles, rbac_custom_roles, rbac_audit,
  pilot_programs, pilot_students
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.core.exceptions import NotFoundError
from app.core.ids import bot_id
from app.core.timefmt import to_wire, to_wire_opt
from app.models.admin_ops import (
    AdminCandidate as AdminCandidateModel,
)
from app.models.admin_ops import (
    AdminCompany as AdminCompanyModel,
)
from app.models.admin_ops import (
    AdminConsoleSnapshot as AdminConsoleSnapshotModel,
)
from app.models.admin_ops import (
    AdminDossier as AdminDossierModel,
)
from app.models.admin_ops import (
    AdminFeatureFlag,
    FlagDef,
    FlagGroup,
    FlagState,
    RbacAuditEntry,
    RbacRole,
)
from app.models.admin_ops import (
    AdminRolePermission as AdminRolePermissionModel,
)
from app.models.admin_ops import (
    AdminSlot as AdminSlotModel,
)
from app.models.admin_ops import (
    AdminVerifier as AdminVerifierModel,
)
from app.models.admin_ops import (
    IntegrityFlag as IntegrityFlagModel,
)
from app.models.admin_ops import (
    PilotProgram as PilotProgramModel,
)
from app.models.admin_ops import (
    PilotStudent as PilotStudentModel,
)
from app.models.admin_ops import (
    RbacCustomRole as RbacCustomRoleModel,
)
from app.models.bot import Bot as BotModel
from app.repositories.bot_repo import BotRepository
from app.repositories.user_repo import UserRepository
from app.schemas.admin_ops import (
    AdminCandidate,
    AdminCompany,
    AdminDashboard,
    AdminDossier,
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
from app.schemas.admin_ops import (
    AdminOverview as AdminOverviewSchema,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{str(ULID()).lower()}"


class AdminOpsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users_repo = UserRepository(db)
        self.bots_repo = BotRepository(db)

    # ── Dashboard / overview / analytics ────────────────────────────────

    async def dashboard(self) -> AdminDashboard:
        row = await self.db.get(AdminConsoleSnapshotModel, "singleton")
        if row is None:
            raise RuntimeError("admin console snapshot seed data missing")
        return AdminDashboard(
            totalUsers=row.total_users, activeCandidates=row.active_candidates,
            activeVerifiers=row.active_verifiers, activeCompanies=row.active_companies,
            sessionsToday=row.sessions_today, reportsThisWeek=row.reports_this_week,
        )

    async def overview(self) -> AdminOverviewSchema:
        row = await self.db.get(AdminConsoleSnapshotModel, "singleton")
        if row is None:
            raise RuntimeError("admin console snapshot seed data missing")
        return AdminOverviewSchema.model_validate({"stats": row.stats, "activity": row.activity})

    async def analytics(self) -> AnalyticsData:
        row = await self.db.get(AdminConsoleSnapshotModel, "singleton")
        if row is None:
            raise RuntimeError("admin console snapshot seed data missing")
        return AnalyticsData.model_validate({
            "topStats": row.top_stats,
            "months": list(row.months),
            "sessions": list(row.sessions),
            "topSkills": row.top_skills,
        })

    # ── Users ────────────────────────────────────────────────────────────
    #
    # Reads/writes the real `users` table directly — the old `admin_users`
    # Mongo collection (a hand-synced duplicate, kept in step via
    # `_propagate_user_update`) is gone per the migration's merge decision.

    async def users(self) -> list[AdminUser]:
        rows = await self.users_repo.list_all()
        return [
            AdminUser(
                id=r.id,
                email=r.email,
                name=f"{r.first_name} {r.last_name}".strip(),
                roles=[role.role for role in r.roles],
                is_active=r.is_active,
                created_at=to_wire(r.created_at),
                last_login=to_wire_opt(r.last_login),
            )
            for r in rows
        ]

    async def update_user_roles(self, user_id: str, roles: list[str]) -> dict[str, Any]:
        updated = await self.users_repo.set_roles(user_id, roles)
        if updated is None:
            raise NotFoundError(f"User {user_id} not found")
        return {"ok": True, "userId": user_id, "roles": roles}

    async def deactivate_user(self, user_id: str) -> dict[str, Any]:
        updated = await self.users_repo.update_by_id(user_id, is_active=False)
        if updated is None:
            raise NotFoundError(f"User {user_id} not found")
        return {"ok": True, "userId": user_id}

    # ── Bots (simple shape — /api/bots) ──────────────────────────────────
    #
    # Reads/writes the real, merged `bots` table (see app.models.bot and
    # app.services.bot_service — the rich-view counterpart).

    @staticmethod
    def _bot_to_simple_schema(row: BotModel) -> Bot:
        status = "paused" if row.status == "inactive" else row.status
        return Bot(
            id=row.id,
            name=row.name,
            description=row.description or "",
            type=row.bot_type or "interviewer",
            model=row.model_label or "",
            status=status,  # type: ignore[arg-type]
            sessionsRun=row.sessions_run,
            avgRating=row.avg_rating if row.avg_rating is not None else 0.0,
            createdAt=to_wire(row.created_at),
        )

    async def simple_bots(self) -> list[Bot]:
        rows = await self.bots_repo.list_all()
        return [self._bot_to_simple_schema(r) for r in rows]

    async def create_simple_bot(self, payload: BotCreate) -> Bot:
        row = await self.bots_repo.insert(
            id=bot_id(),
            name=payload.name or "New Bot",
            description=payload.description or "",
            bot_type=payload.type or "interviewer",
            model_label=payload.model or "claude-opus-4-7",
            status="draft",
            sessions_run=0,
            avg_rating=0.0,
        )
        return self._bot_to_simple_schema(row)

    # ── Feature flags (simple list — /api/admin/feature-flags) ──────────

    async def feature_flags(self) -> list[FeatureFlag]:
        stmt = select(AdminFeatureFlag).order_by(AdminFeatureFlag.key)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            FeatureFlag(key=r.key, name=r.name, description=r.description, enabled=r.enabled, scope=r.scope)  # type: ignore[arg-type]
            for r in rows
        ]

    async def update_feature_flag(self, key: str, enabled: bool) -> FeatureFlag:
        row = await self.db.get(AdminFeatureFlag, key)
        if row is None:
            raise NotFoundError(f"Feature flag {key} not found")
        row.enabled = enabled
        await self.db.flush()
        return FeatureFlag(key=row.key, name=row.name, description=row.description, enabled=row.enabled, scope=row.scope)  # type: ignore[arg-type]

    # ── Role permissions (simple list — /api/admin/permissions) ─────────

    async def permissions(self) -> list[RolePermission]:
        stmt = select(AdminRolePermissionModel).order_by(AdminRolePermissionModel.role)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [RolePermission(role=r.role, permissions=list(r.permissions)) for r in rows]

    # ── Dossiers ─────────────────────────────────────────────────────────

    @staticmethod
    def _dossier_to_schema(row: AdminDossierModel) -> AdminDossier:
        return AdminDossier(
            id=row.id, candidate=row.candidate, skill=row.skill, verifier=row.verifier,
            date=row.date, score=row.score, status=row.status,  # type: ignore[arg-type]
        )

    async def dossiers(self) -> list[AdminDossier]:
        stmt = select(AdminDossierModel).order_by(AdminDossierModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._dossier_to_schema(r) for r in rows]

    async def create_dossier(self, payload: DossierCreate) -> AdminDossier:
        row = AdminDossierModel(
            id=_new_id("svr"),
            candidate=payload.candidate or "",
            skill=payload.skill or "",
            verifier=payload.verifier or "",
            date=payload.date or datetime.now(timezone.utc).strftime("%b %d"),
            score=payload.score or 0,
            status=payload.status or "draft",
        )
        self.db.add(row)
        await self.db.flush()
        return self._dossier_to_schema(row)

    async def patch_dossier(self, dossier_id: str, patch: DossierPatch) -> AdminDossier:
        row = await self.db.get(AdminDossierModel, dossier_id)
        if row is None:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        diff = patch.model_dump(exclude_unset=True)
        for k, v in diff.items():
            setattr(row, k, v)
        if diff:
            await self.db.flush()
        return self._dossier_to_schema(row)

    async def publish_dossier(self, dossier_id: str) -> dict[str, Any]:
        row = await self.db.get(AdminDossierModel, dossier_id)
        if row is None:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        row.status = "published"
        await self.db.flush()
        return {"ok": True}

    async def delete_dossier(self, dossier_id: str) -> dict[str, Any]:
        row = await self.db.get(AdminDossierModel, dossier_id)
        if row is None:
            raise NotFoundError(f"Dossier {dossier_id} not found")
        await self.db.delete(row)
        await self.db.flush()
        return {"ok": True}

    # ── Slots (admin view) ───────────────────────────────────────────────

    @staticmethod
    def _slot_to_schema(row: AdminSlotModel) -> AdminSlot:
        return AdminSlot(
            id=row.id, verifier=row.verifier, day=row.day, time=row.time, duration=row.duration,
            skill=row.skill, booked=row.booked, candidate=row.candidate,
        )

    async def slots(self) -> list[AdminSlot]:
        stmt = select(AdminSlotModel).order_by(AdminSlotModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._slot_to_schema(r) for r in rows]

    async def create_slot(self, payload: AdminSlotCreate) -> AdminSlot:
        row = AdminSlotModel(
            id=_new_id("slt"),
            verifier=payload.verifier or "Unassigned",
            day=payload.day or "",
            time=payload.time or "",
            duration=payload.duration or 60,
            skill=payload.skill or "Any",
            booked=False,
        )
        self.db.add(row)
        await self.db.flush()
        return self._slot_to_schema(row)

    async def block_slot(self, slot_id: str) -> dict[str, Any]:
        """Mock parity: blocking removes the slot from the pool."""
        row = await self.db.get(AdminSlotModel, slot_id)
        if row is None:
            raise NotFoundError(f"Slot {slot_id} not found")
        await self.db.delete(row)
        await self.db.flush()
        return {"ok": True}

    # ── Verifiers (admin roster) ─────────────────────────────────────────

    @staticmethod
    def _verifier_to_schema(row: AdminVerifierModel) -> AdminVerifier:
        return AdminVerifier(
            id=row.id, name=row.name, specialization=row.specialization, sessions=row.sessions,
            rating=row.rating, quality=row.quality, since=row.since, tier=row.tier,  # type: ignore[arg-type]
            experience=row.experience, applied=row.applied, sample=row.sample,  # type: ignore[arg-type]
        )

    async def verifiers(self) -> list[AdminVerifier]:
        stmt = select(AdminVerifierModel).order_by(AdminVerifierModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._verifier_to_schema(r) for r in rows]

    async def invite_verifier(self, payload: VerifierInviteRequest) -> dict[str, Any]:
        # Mock parity: the invite is acknowledged but creates no roster row.
        return {"ok": True, "email": payload.email, "specialization": payload.specialization}

    async def approve_verifier(self, verifier_id: str) -> dict[str, Any]:
        row = await self.db.get(AdminVerifierModel, verifier_id)
        if row is None:
            raise NotFoundError(f"Verifier {verifier_id} not found")
        row.tier = "active"
        row.since = "Apr 2026"
        await self.db.flush()
        return {"ok": True}

    async def suspend_verifier(self, verifier_id: str) -> dict[str, Any]:
        row = await self.db.get(AdminVerifierModel, verifier_id)
        if row is None:
            raise NotFoundError(f"Verifier {verifier_id} not found")
        row.tier = "probation"
        await self.db.flush()
        return {"ok": True}

    # ── Candidates / companies (admin views) ─────────────────────────────

    async def candidates(self) -> list[AdminCandidate]:
        stmt = select(AdminCandidateModel).order_by(AdminCandidateModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            AdminCandidate(
                id=r.id, name=r.name, location=r.location, verifications=r.verifications,
                topScore=r.top_score, lastSession=r.last_session, status=r.status,  # type: ignore[arg-type]
            )
            for r in rows
        ]

    async def companies(self) -> list[AdminCompany]:
        stmt = select(AdminCompanyModel).order_by(AdminCompanyModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            AdminCompany(
                id=r.id, name=r.name, plan=r.plan, seats=r.seats, seatsUsed=r.seats_used,  # type: ignore[arg-type]
                chats=r.chats, followups=r.followups, since=r.since, status=r.status,  # type: ignore[arg-type]
            )
            for r in rows
        ]

    async def impersonate_company(self, company_id: str) -> dict[str, Any]:
        row = await self.db.get(AdminCompanyModel, company_id)
        if row is None:
            raise NotFoundError(f"Company {company_id} not found")
        return {"ok": True, "sessionId": _new_id("imp"), "companyId": company_id}

    # ── Integrity ────────────────────────────────────────────────────────

    async def integrity(self) -> IntegrityEnvelope:
        stmt = select(IntegrityFlagModel).order_by(IntegrityFlagModel.id)
        flags = (await self.db.execute(stmt)).scalars().all()
        signals_row = await self.db.get(AdminConsoleSnapshotModel, "singleton")
        if signals_row is None:
            raise RuntimeError("admin console snapshot seed data missing")
        return IntegrityEnvelope.model_validate({
            "flags": [
                {"id": f.id, "summary": f.summary, "refId": f.ref_id, "severity": f.severity,
                 "date": f.date, "action": f.action}
                for f in flags
            ],
            "signals": signals_row.items,
        })

    async def resolve_integrity_flag(self, flag_id: str, action: str | None) -> dict[str, Any]:
        row = await self.db.get(IntegrityFlagModel, flag_id)
        if row is None:
            raise NotFoundError(f"Integrity flag {flag_id} not found")
        row.severity = "confirmed"
        row.action = action or "Resolved"
        await self.db.flush()
        return {"ok": True}

    # ── Feature flags (rich registry + state — /api/admin/flags) ────────

    async def _flag_registry(self) -> list[dict[str, Any]]:
        stmt = select(FlagGroup).order_by(FlagGroup.id)
        groups = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "group": g.name,
                "flags": [
                    {"id": d.id, "label": d.label, "desc": d.description, "default": d.default}
                    for d in g.defs
                ],
            }
            for g in groups
        ]

    async def _flag_state(self) -> dict[str, bool]:
        stmt = select(FlagState)
        rows = (await self.db.execute(stmt)).scalars().all()
        return {r.flag_id: r.enabled for r in rows}

    async def flags(self) -> FlagsEnvelope:
        return FlagsEnvelope.model_validate(
            {"registry": await self._flag_registry(), "state": await self._flag_state()}
        )

    async def _flag_state_rows(self) -> dict[str, FlagState]:
        """Every flag-state row in ONE query (H2). The per-flag `db.get`
        loops below were N+1 — resetting 33 flags cost ~35 round-trips.
        """
        stmt = select(FlagState)
        return {row.flag_id: row for row in (await self.db.execute(stmt)).scalars().all()}

    @staticmethod
    def _state_values(rows: dict[str, FlagState]) -> dict[str, bool]:
        return {flag_id: row.enabled for flag_id, row in rows.items()}

    async def update_flags(self, patch: dict[str, bool]) -> dict[str, Any]:
        rows = await self._flag_state_rows()
        for flag_id, enabled in patch.items():
            row = rows.get(flag_id)
            if row is not None:  # unknown ids stay no-ops (mock parity)
                row.enabled = enabled
        await self.db.flush()
        return {"ok": True, "state": self._state_values(rows)}

    async def reset_flags(self) -> dict[str, Any]:
        stmt = select(FlagDef)
        defs = (await self.db.execute(stmt)).scalars().all()
        rows = await self._flag_state_rows()
        for d in defs:
            row = rows.get(d.id)
            if row is not None:
                row.enabled = d.default
        await self.db.flush()
        return {"ok": True, "state": self._state_values(rows)}

    async def toggle_flag_group(self, group_name: str, value: bool) -> dict[str, Any]:
        stmt = select(FlagGroup).where(FlagGroup.name == group_name)
        group = (await self.db.execute(stmt)).scalar_one_or_none()
        if group is not None:
            rows = await self._flag_state_rows()
            for d in group.defs:
                row = rows.get(d.id)
                if row is not None:
                    row.enabled = value
            await self.db.flush()
            state = self._state_values(rows)
        else:
            state = await self._flag_state()
        # Mock parity: unknown groups are a no-op that still returns ok+state.
        return {"ok": True, "state": state}

    # ── RBAC ─────────────────────────────────────────────────────────────

    async def rbac(self) -> RbacEnvelope:
        stmt = select(RbacRole).order_by(RbacRole.order_seq)
        roles = (await self.db.execute(stmt)).scalars().all()
        stmt2 = select(RbacCustomRoleModel).order_by(RbacCustomRoleModel.id)
        customs = (await self.db.execute(stmt2)).scalars().all()
        stmt3 = select(RbacAuditEntry).order_by(RbacAuditEntry.id)
        audit = (await self.db.execute(stmt3)).scalars().all()
        return RbacEnvelope.model_validate({
            "roles": [
                {
                    "id": r.id, "label": r.label, "color": r.color,
                    "perms": [
                        {"id": p["perm_id"], "label": p["label"], "on": p["on"], "locked": p["locked"]}
                        for p in r.perms
                    ],
                }
                for r in roles
            ],
            "customRoles": [
                {"id": c.id, "name": c.name, "baseRole": c.base_role, "desc": c.description,
                 "members": c.members, "overrides": c.overrides}
                for c in customs
            ],
            "audit": [
                {"id": a.id, "time": a.time, "actor": a.actor, "action": a.action, "detail": a.detail}
                for a in audit
            ],
        })

    async def set_role_permission(self, role_id: str, perm_id: str, on: bool) -> dict[str, Any]:
        role = await self.db.get(RbacRole, role_id)
        if role is None:
            raise NotFoundError(f"Role {role_id} not found")
        # Locked permissions never flip; unknown perm ids are a no-op
        # (mock parity — the handler still answers {ok: true}). Reassign
        # the whole list (not an in-place dict mutation) so SQLAlchemy's
        # JSONB change tracking picks it up.
        role.perms = [
            {**p, "on": on} if p["perm_id"] == perm_id and not p["locked"] else p
            for p in role.perms
        ]
        await self.db.flush()
        return {"ok": True}

    async def create_custom_role(self, payload: CustomRoleCreate) -> CustomRole:
        row = RbacCustomRoleModel(
            id=_new_id("cr"),
            name=payload.name or "New role",
            base_role=payload.baseRole or "candidate",
            description=payload.desc or "",
            members=0,
            overrides=dict(payload.overrides or {}),
        )
        self.db.add(row)
        await self.db.flush()
        return CustomRole(
            id=row.id, name=row.name, baseRole=row.base_role, desc=row.description,  # type: ignore[arg-type]
            members=row.members, overrides=row.overrides,
        )

    async def delete_custom_role(self, role_id: str) -> dict[str, Any]:
        row = await self.db.get(RbacCustomRoleModel, role_id)
        if row is None:
            raise NotFoundError(f"Custom role {role_id} not found")
        await self.db.delete(row)
        await self.db.flush()
        return {"ok": True}

    # ── Pilots ───────────────────────────────────────────────────────────

    @staticmethod
    def _pilot_to_schema(row: PilotProgramModel) -> PilotProgram:
        return PilotProgram(
            id=row.id, name=row.name, college=row.college, batch=row.batch,
            coordinator=row.coordinator, students=row.students, completed=row.completed,
            avgScore=row.avg_score, status=row.status,  # type: ignore[arg-type]
            startDate=row.start_date, endDate=row.end_date,
            dept=row.dept, assessments=list(row.assessments),
        )

    async def pilots_simple(self) -> list[PilotProgramSimple]:
        # Same table as pilots-full; the simple schema just omits
        # dept/assessments from what it constructs.
        stmt = select(PilotProgramModel).order_by(PilotProgramModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            PilotProgramSimple(
                id=r.id, name=r.name, college=r.college, batch=r.batch, coordinator=r.coordinator,
                students=r.students, completed=r.completed, avgScore=r.avg_score,
                status=r.status, startDate=r.start_date, endDate=r.end_date,  # type: ignore[arg-type]
            )
            for r in rows
        ]

    async def pilots_full(self) -> list[PilotProgram]:
        stmt = select(PilotProgramModel).order_by(PilotProgramModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._pilot_to_schema(r) for r in rows]

    async def create_pilot(self, payload: PilotProgramCreate) -> PilotProgram:
        row = PilotProgramModel(
            id=_new_id("plt"),
            name=payload.name or "New pilot",
            college=payload.college or "",
            dept=payload.dept or "Computer Science",
            batch=payload.batch or "2024-25",
            coordinator=payload.coordinator or "",
            status="draft",
            students=0,
            completed=0,
            avg_score=0,
            start_date=payload.startDate or "",
            end_date=payload.endDate or "",
            assessments=list(payload.assessments or []),
        )
        self.db.add(row)
        await self.db.flush()
        return self._pilot_to_schema(row)

    # ── Pilot students ───────────────────────────────────────────────────

    @staticmethod
    def _student_to_schema(row: PilotStudentModel) -> PilotStudent:
        return PilotStudent(
            id=row.id, name=row.name, email=row.email, program=row.program,
            completed=row.completed, pending=row.pending, avgScore=row.avg_score,
            status=row.status,  # type: ignore[arg-type]
        )

    async def pilot_students(self) -> list[PilotStudent]:
        stmt = select(PilotStudentModel).order_by(PilotStudentModel.id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._student_to_schema(r) for r in rows]

    async def _bump_program_students(self, counts: dict[str, int]) -> None:
        """Increment each program's `students` count. Unknown program ids
        are skipped (mock parity — the student row is still created)."""
        for program_id, n in counts.items():
            # SQL-side increment; a Python `+=` loses updates under concurrency.
            await self.db.execute(
                update(PilotProgramModel)
                .where(PilotProgramModel.id == program_id)
                .values(students=PilotProgramModel.students + n)
                .execution_options(synchronize_session="fetch")
            )
        await self.db.flush()

    def _new_student_row(self, payload: PilotStudentCreate) -> PilotStudentModel:
        return PilotStudentModel(
            id=_new_id("stu"),
            name=payload.name,
            email=payload.email,
            program=payload.program,
            completed=0,
            pending=3,
            avg_score=0,
            status="registered",
        )

    async def create_pilot_student(self, payload: PilotStudentCreate) -> PilotStudent:
        row = self._new_student_row(payload)
        self.db.add(row)
        await self.db.flush()
        await self._bump_program_students({payload.program: 1})
        return self._student_to_schema(row)

    async def import_pilot_students(self, rows: list[PilotStudentCreate]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for payload in rows:
            self.db.add(self._new_student_row(payload))
            counts[payload.program] = counts.get(payload.program, 0) + 1
        await self.db.flush()
        await self._bump_program_students(counts)
        return {"ok": True, "count": len(rows)}
