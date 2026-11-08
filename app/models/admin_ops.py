"""Admin ops storage layer — dashboards, flags, RBAC, pilots.

Singleton rows use a fixed `id="singleton"` PK. Ordered child lists use
an autoincrement surrogate PK with `order_by="<Child>.id"` to preserve
seed insertion order; `rbac_roles` uses an explicit `order_seq` column
instead since its display order isn't alphabetical. Feature flags are
three tables (`flag_groups`, `flag_defs`, `flag_state`) rather than one
JSON blob, so each flag is independently updatable.
"""

from typing import Any, Optional

from sqlalchemy import ARRAY, Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.user import _ROLES as _USER_ROLES

_DOSSIER_STATUSES = ("published", "in-review", "draft", "archived")
_VERIFIER_QUALITY = ("Exemplary", "Strong", "Probation")
_VERIFIER_TIER = ("active", "applicants", "probation")
_VERIFIER_SAMPLE = ("Reviewed", "Pending")
_CANDIDATE_STATUSES = ("active", "blacklisted")
_COMPANY_PLANS = ("Starter", "Growth", "Enterprise")
_COMPANY_STATUSES = ("active", "trial", "churned")
_INTEGRITY_SEVERITY = ("high", "medium", "confirmed")
_FLAG_SCOPES = ("global", "candidate", "verifier", "company")
_RBAC_ROLE_IDS = ("candidate", "verifier", "company", "admin")
_PILOT_STATUSES = ("active", "draft", "completed")
_PILOT_STUDENT_STATUSES = ("active", "registered")


# ─── Console snapshot (merged singleton) ─────────────────────────────────


class AdminConsoleSnapshot(Base, TimestampMixin):
    """Single row (`id = "singleton"`) holding every pre-aggregated admin
    console payload — dashboard counts, overview stats/activity,
    analytics series, and integrity signals.

    Merged from the four former singletons `admin_dashboard`,
    `admin_overview`, `admin_analytics`, `integrity_signals`: all four were seed-once/read-always single-row tables
    with no FKs into them and no runtime writes, i.e. four views over one
    entity ("the admin console's snapshot data"), not four independently
    managed facts. Section-prefixed comments below mark which former
    table each column set came from.
    """

    __tablename__ = "admin_console_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="singleton")

    # ── former admin_dashboard ─────────────────────────────────────────
    total_users: Mapped[int] = mapped_column(Integer, nullable=False)
    active_candidates: Mapped[int] = mapped_column(Integer, nullable=False)
    active_verifiers: Mapped[int] = mapped_column(Integer, nullable=False)
    active_companies: Mapped[int] = mapped_column(Integer, nullable=False)
    sessions_today: Mapped[int] = mapped_column(Integer, nullable=False)
    reports_this_week: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── former admin_overview ──────────────────────────────────────────
    # Small, never independently queried lists — JSONB, not child tables.
    stats: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    activity: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # ── former admin_analytics ─────────────────────────────────────────
    # Flat parallel arrays — always read/written together as one series,
    # nothing joins to an individual month/session-count pair.
    months: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    sessions: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)

    # Small, never independently queried lists — JSONB, not child tables.
    top_stats: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    top_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # ── former integrity_signals ───────────────────────────────────────
    # Small, never independently queried list — JSONB, not a child table.
    # `status` here is a free-text description ("Active · 186 verifiers
    # enrolled"), not a bounded enum — see app/models/admin_ops.py history.
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


# ─── Integrity flags ───────────────────────────────────────────────────


class IntegrityFlag(Base, TimestampMixin):
    __tablename__ = "integrity_flags"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(
        Enum(*_INTEGRITY_SEVERITY, name="integrity_severity", native_enum=False, create_constraint=True),
        nullable=False,
    )
    date: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)


# ─── Feature flags — simple list + role permissions (simple list) ───────


class AdminFeatureFlag(Base, TimestampMixin):
    __tablename__ = "admin_feature_flags"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope: Mapped[str] = mapped_column(
        Enum(*_FLAG_SCOPES, name="admin_feature_flag_scope", native_enum=False, create_constraint=True),
        nullable=False,
    )


class AdminRolePermission(Base, TimestampMixin):
    __tablename__ = "admin_role_permissions"

    # Reuses `users.user_roles.role`'s value set/CHECK constraint name —
    # same 5-role vocabulary (candidate/company/interviewer/hr/admin), not
    # the separate 4-value RBAC role set (`_RBAC_ROLE_IDS` above).
    role: Mapped[str] = mapped_column(
        Enum(*_USER_ROLES, name="user_role_value", native_enum=False, create_constraint=True),
        primary_key=True,
    )
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)


# ─── Dossiers / slots / verifiers / candidates / companies (admin views) ─


class AdminDossier(Base, TimestampMixin):
    __tablename__ = "admin_dossiers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Nullable — only published reports have a matching full detail record
    # (e.g. draft/in-review admin_dossiers rows never do). See
    # app/models/candidate.py's SkillReport.report_id for the same pattern.
    report_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("skill_report_details.id", ondelete="SET NULL"), nullable=True, index=True
    )
    candidate: Mapped[str] = mapped_column(String(200), nullable=False)
    skill: Mapped[str] = mapped_column(String(200), nullable=False)
    verifier: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        Enum(*_DOSSIER_STATUSES, name="admin_dossier_status", native_enum=False, create_constraint=True),
        nullable=False,
    )


class AdminSlot(Base, TimestampMixin):
    __tablename__ = "admin_slots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    verifier: Mapped[str] = mapped_column(String(200), nullable=False)
    day: Mapped[str] = mapped_column(String(20), nullable=False)
    time: Mapped[str] = mapped_column(String(20), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    booked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candidate: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class AdminVerifier(Base, TimestampMixin):
    __tablename__ = "admin_verifiers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Nullable — this roster is a broader population than registered
    # accounts (most rows have no login at all); set only for rows that
    # are confirmed to correspond to a real user (see seed_admin_ops.py).
    linked_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    specialization: Mapped[str] = mapped_column(String(200), nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    quality: Mapped[str] = mapped_column(
        Enum(*_VERIFIER_QUALITY, name="admin_verifier_quality", native_enum=False, create_constraint=True),
        nullable=False,
    )
    since: Mapped[str] = mapped_column(String(20), nullable=False)
    tier: Mapped[str] = mapped_column(
        Enum(*_VERIFIER_TIER, name="admin_verifier_tier", native_enum=False, create_constraint=True),
        nullable=False,
    )
    experience: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    applied: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sample: Mapped[Optional[str]] = mapped_column(
        Enum(*_VERIFIER_SAMPLE, name="admin_verifier_sample", native_enum=False, create_constraint=True),
        nullable=True,
    )


class AdminCandidate(Base, TimestampMixin):
    __tablename__ = "admin_candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Nullable — see AdminVerifier.linked_user_id.
    linked_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    verifications: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_session: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_CANDIDATE_STATUSES, name="admin_candidate_status", native_enum=False, create_constraint=True),
        nullable=False,
    )


class AdminCompany(Base, TimestampMixin):
    __tablename__ = "admin_companies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Nullable — this roster covers many companies; `companies` is a
    # singleton for the one this demo backend's portal serves, so only
    # the matching row (if any) gets linked. See AdminVerifier.linked_user_id.
    linked_company_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[str] = mapped_column(
        Enum(*_COMPANY_PLANS, name="admin_company_plan", native_enum=False, create_constraint=True),
        nullable=False,
    )
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seats_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    followups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    since: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_COMPANY_STATUSES, name="admin_company_status", native_enum=False, create_constraint=True),
        nullable=False,
    )


# ─── Feature flags — rich registry + state ───────────────────────────────


class FlagGroup(Base):
    __tablename__ = "flag_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    defs: Mapped[list["FlagDef"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", lazy="selectin", order_by="FlagDef.id"
    )


class FlagDef(Base):
    __tablename__ = "flag_defs"

    # Natural id, e.g. "candidate.public_profile" — already globally
    # unique across every group, and it's what FlagState/patches key on.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("flag_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default: Mapped[bool] = mapped_column(Boolean, nullable=False)

    group: Mapped["FlagGroup"] = relationship(back_populates="defs")


class FlagState(Base, TimestampMixin):
    """Current on/off value per flag — decomposed from the old
    `admin_flag_state` singleton dict-blob so each flag's state is an
    independently-updatable row instead of one giant JSON document
    rewritten on every toggle."""

    __tablename__ = "flag_state"

    flag_id: Mapped[str] = mapped_column(ForeignKey("flag_defs.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


# ─── RBAC ────────────────────────────────────────────────────────────────


class RbacRole(Base):
    __tablename__ = "rbac_roles"

    id: Mapped[str] = mapped_column(
        Enum(*_RBAC_ROLE_IDS, name="rbac_role_id", native_enum=False, create_constraint=True), primary_key=True
    )
    # UI display order (candidate, verifier, company, admin) isn't
    # alphabetical, so it can't ride on the string PK the way most other
    # admin-ops lists do.
    order_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    color: Mapped[str] = mapped_column(String(60), nullable=False)

    # Small, never independently queried list — JSONB, not a child table.
    # `set_role_permission()` reassigns the whole list on every toggle
    # (not an in-place dict mutation) so SQLAlchemy's change tracking sees it.
    perms: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class RbacCustomRole(Base, TimestampMixin):
    __tablename__ = "rbac_custom_roles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_role: Mapped[str] = mapped_column(
        Enum(*_RBAC_ROLE_IDS, name="rbac_custom_role_base", native_enum=False, create_constraint=True),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Genuinely opaque, non-cross-referenced per-role override blob.
    overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class RbacAuditEntry(Base, TimestampMixin):
    __tablename__ = "rbac_audit"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    time: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)


# ─── Pilots ──────────────────────────────────────────────────────────────


class PilotProgram(Base, TimestampMixin):
    __tablename__ = "pilot_programs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    college: Mapped[str] = mapped_column(String(200), nullable=False)
    dept: Mapped[str] = mapped_column(String(200), nullable=False)
    batch: Mapped[str] = mapped_column(String(40), nullable=False)
    coordinator: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*_PILOT_STATUSES, name="pilot_program_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="draft",
    )
    # Maintained counter — bumped in the same transaction as each new
    # PilotStudent insert, never recomputed by scanning pilot_students at
    # read time (per the migration plan's maintained-aggregates standard).
    students: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_date: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    end_date: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    # Soft, non-FK references to assessment ids (mock parity: seed data
    # references legacy "ASS-xxx" ids, not the real ULID-based ones).
    assessments: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)


class PilotStudent(Base, TimestampMixin):
    __tablename__ = "pilot_students"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Soft reference, like `interviewer_approvals.candidate_id` — mock
    # parity: `_bump_program_students` silently no-ops on an unknown
    # program id (still creates the student row), which a hard FK would
    # reject outright.
    program: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    avg_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        Enum(*_PILOT_STUDENT_STATUSES, name="pilot_student_status", native_enum=False, create_constraint=True),
        nullable=False,
        default="registered",
    )
