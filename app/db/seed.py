"""Idempotent startup seeding.

Mirrors the frontend's mock seed data so a fresh stack boots with the
same five personas the UI's dev-login buttons expect. Upserts by `id`
(existence-checked via `session.get`/a `SELECT`), so re-running on every
startup is safe and edits made at runtime to non-seeded fields survive.

Future modules add their own `seed_*` functions here and register them
in `run_seeds()`.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import parse_wire

log = logging.getLogger(__name__)




# ── Users ───────────────────────────────────────────────────────────────
#
# Source: anveksha_ui/src/mocks/data/users.ts (seedUsers + specialistUser).

SEED_USERS: list[dict] = [
    {
        "id": "usr_cand_001",
        "email": "aarav.rao@anveksha.dev",
        "first_name": "Aarav",
        "last_name": "Rao",
        "user_name": "aarav.rao",
        "roles": ["candidate"],
        "is_active": True,
        "created_at": "2025-08-12T09:00:00.000Z",
    },
    {
        "id": "usr_ver_001",
        "email": "maya.iyer@anveksha.dev",
        "first_name": "Maya",
        "last_name": "Iyer",
        "user_name": "maya.iyer",
        # Freelance interviewers are also candidates — promoted from the pool.
        "roles": ["candidate", "interviewer"],
        "is_active": True,
        "created_at": "2025-07-20T09:00:00.000Z",
    },
    {
        "id": "usr_spec_001",
        "email": "suresh.mehra@anveksha.dev",
        "first_name": "Suresh",
        "last_name": "Mehra",
        "user_name": "suresh.mehra",
        # Specialist — interviewer role conferred by admin, never assessed.
        "roles": ["candidate", "interviewer"],
        "is_active": True,
        "created_at": "2025-09-01T09:00:00.000Z",
    },
    {
        "id": "usr_co_001",
        "email": "priya.menon@northstack.co",
        "first_name": "Priya",
        "last_name": "Menon",
        "user_name": "priya.menon",
        "roles": ["company"],
        "is_active": True,
        "created_at": "2025-06-15T09:00:00.000Z",
    },
    {
        "id": "usr_hr_001",
        "email": "rohan.shah@northstack.co",
        "first_name": "Rohan",
        "last_name": "Shah",
        "user_name": "rohan.shah",
        "roles": ["hr", "company"],
        "is_active": True,
        "created_at": "2025-06-15T09:00:00.000Z",
    },
    {
        "id": "usr_adm_001",
        "email": "admin@anveksha.dev",
        "first_name": "Anveksha",
        "last_name": "Admin",
        "user_name": "admin",
        "roles": ["admin"],
        "is_active": True,
        "created_at": "2025-01-01T09:00:00.000Z",
    },
    # ── Real Google-account users ────────────────────────────────────────
    # These sign in through the actual Google OAuth flow (frontend
    # GoogleLogin button → /api/auth/google-register with a real ID
    # token). Seeded so their roles are assigned before first login.
    {
        "id": "usr_cand_rajesh",
        "email": "rajesh.rudravarjula@gmail.com",
        "first_name": "Rajesh",
        "last_name": "Rudravarjula",
        "user_name": "rajesh.rudravarjula",
        "roles": ["candidate"],
        "is_active": True,
        "created_at": "2026-06-01T09:00:00.000Z",
    },
    {
        "id": "usr_adm_rajesh",
        "email": "rudrravarjula1234@gmail.com",
        "first_name": "Rajesh",
        "last_name": "Rudravarjula",
        "user_name": "rudrravarjula1234",
        "roles": ["admin"],
        "is_active": True,
        "created_at": "2026-06-01T09:00:00.000Z",
    },
]


async def seed_users(db: AsyncSession) -> int:
    """Insert any missing seed users (Postgres). Returns how many were
    inserted. Takes an explicit session so callers — the app lifespan, or
    a test fixture's transactional session — control exactly which
    session/transaction the writes land in."""
    from app.repositories.user_repo import UserRepository

    repo = UserRepository(db)
    inserted = 0
    for template in SEED_USERS:
        existing = await repo.find_by_id(template["id"])
        if existing:
            continue
        fields = {k: v for k, v in template.items() if k != "roles"}
        fields["created_at"] = parse_wire(fields["created_at"])
        await repo.insert_with_roles(roles=template["roles"], **fields)
        inserted += 1
    return inserted


async def seeds_present(db: AsyncSession) -> bool:
    """Startup fast-path (H1): has a previous boot already committed the
    full seed set?

    `run_seeds()` executes every seeder in ONE transaction committed by the
    lifespan (no seeder commits internally) and `workflow_runs` is seeded
    LAST — so a row there means every earlier seeder landed in the same
    commit. Skipping the replay turns a warm restart from ~260 queries /
    ~1.1 s into a single marker query. Test fixtures call `run_seeds()`
    directly (and roll their work back), so they never trip this guard.
    """
    from app.models.workflow import WorkflowRun

    stmt = select(WorkflowRun.workflow_id).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def run_seeds(db: AsyncSession) -> None:
    """Run every registered seeder. Called from the app lifespan (and
    directly by test fixtures, since ASGITransport doesn't run it).

    `db` is the Postgres session shared by every seeder below.
    """
    from app.db.seed_admin_ops import seed_admin_ops, seed_simple_bots
    from app.db.seed_agent_registry import seed_agent_registry
    from app.db.seed_approvals import seed_approvals
    from app.db.seed_assessments import seed_assessments, seed_coupons
    from app.db.seed_candidate import seed_candidate
    from app.db.seed_company import seed_company
    from app.db.seed_ledgers import seed_skill_ledgers
    from app.db.seed_metrics import seed_metrics
    from app.db.seed_portal import seed_portal
    from app.db.seed_verifier import seed_verifier

    n_users = await seed_users(db)
    if n_users:
        log.info("Seeded %d user(s).", n_users)
    # bots before ai_models-referencing / assessments (both FK into bots
    # and ai_models) and agent_registry (FK into ai_models) — dependency
    # order matters now that these are real foreign keys, not soft Mongo
    # references. ai_models itself has no seed data (admin-created only).
    n_simple_bots = await seed_simple_bots(db)
    if n_simple_bots:
        log.info("Seeded %d bot(s) (simple view).", n_simple_bots)
    n_agents = await seed_agent_registry(db)
    if n_agents:
        log.info("Seeded %d agent config(s).", n_agents)
    n_ledgers = await seed_skill_ledgers(db)
    if n_ledgers:
        log.info("Seeded %d skill ledger(s).", n_ledgers)
    n_assessments = await seed_assessments(db)
    if n_assessments:
        log.info("Seeded %d assessment(s).", n_assessments)
    n_coupons = await seed_coupons(db)
    if n_coupons:
        log.info("Seeded %d coupon(s).", n_coupons)
    # candidate before verifier — session_reports.published_report_id FKs
    # into skill_report_details, seeded by seed_candidate.
    n_candidate = await seed_candidate(db)
    if n_candidate:
        log.info("Seeded %d candidate doc(s).", n_candidate)
    n_verifier = await seed_verifier(db)
    if n_verifier:
        log.info("Seeded %d verifier doc(s).", n_verifier)
    n_portal = await seed_portal(db)
    if n_portal:
        log.info("Seeded %d portal doc(s).", n_portal)
    n_approvals = await seed_approvals(db)
    if n_approvals:
        log.info("Seeded %d approvals doc(s).", n_approvals)
    n_company = await seed_company(db)
    if n_company:
        log.info("Seeded %d company doc(s).", n_company)
    n_admin_ops = await seed_admin_ops(db)
    if n_admin_ops:
        log.info("Seeded %d admin-ops doc(s).", n_admin_ops)
    n_metrics = await seed_metrics(db)
    if n_metrics:
        log.info("Seeded %d metrics doc(s).", n_metrics)
