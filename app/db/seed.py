"""Idempotent startup seeding.

Mirrors the frontend's mock seed data so a fresh stack boots with the
same five personas the UI's dev-login buttons expect. Upserts by `id`,
so re-running on every startup is safe and edits made at runtime to
non-seeded fields survive (we only $setOnInsert the document).

Future modules add their own `seed_*` functions here and register them
in `run_seeds()`.
"""

import logging
from datetime import datetime, timezone

from app.db.mongo import get_database

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
]


async def seed_users() -> int:
    """Insert any missing seed users. Returns how many were inserted."""
    db = get_database()
    users = db["users"]
    inserted = 0
    for template in SEED_USERS:
        existing = await users.find_one({"id": template["id"]})
        if existing:
            continue
        doc = dict(template)
        doc["updated_at"] = _now_iso()
        doc["last_login"] = None
        await users.insert_one(doc)
        inserted += 1
    return inserted


async def run_seeds() -> None:
    """Run every registered seeder. Called from the app lifespan."""
    from app.db.seed_assessments import seed_assessments, seed_coupons
    from app.db.seed_ledgers import seed_skill_ledgers
    from app.db.seed_verifier import seed_verifier

    n_users = await seed_users()
    if n_users:
        log.info("Seeded %d user(s).", n_users)
    n_ledgers = await seed_skill_ledgers()
    if n_ledgers:
        log.info("Seeded %d skill ledger(s).", n_ledgers)
    n_assessments = await seed_assessments()
    if n_assessments:
        log.info("Seeded %d assessment(s).", n_assessments)
    n_coupons = await seed_coupons()
    if n_coupons:
        log.info("Seeded %d coupon(s).", n_coupons)
    n_verifier = await seed_verifier()
    if n_verifier:
        log.info("Seeded %d verifier doc(s).", n_verifier)
    from app.db.seed_candidate import seed_candidate

    n_candidate = await seed_candidate()
    if n_candidate:
        log.info("Seeded %d candidate doc(s).", n_candidate)
    from app.db.seed_portal import seed_portal

    n_portal = await seed_portal()
    if n_portal:
        log.info("Seeded %d portal doc(s).", n_portal)
    from app.db.seed_approvals import seed_approvals

    n_approvals = await seed_approvals()
    if n_approvals:
        log.info("Seeded %d approvals doc(s).", n_approvals)
