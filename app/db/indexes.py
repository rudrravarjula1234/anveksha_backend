"""Index creation invoked once on app startup.

Idempotent — Mongo's `create_index` is a no-op when the same index
already exists. Adding a new index here ships with the next deploy.
"""

import logging

from app.db.mongo import get_database

log = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    db = get_database()

    # Models — `id` is our app-level id (ULID-prefixed), distinct from Mongo `_id`.
    await db.ai_models.create_index("id", unique=True)
    await db.ai_models.create_index("model")  # frequently queried
    await db.ai_models.create_index("status")

    # Bots
    await db.bots.create_index("id", unique=True)
    await db.bots.create_index("primaryModelId")
    await db.bots.create_index("status")
    await db.bots.create_index("specializations")  # multikey

    # Users
    await db["users"].create_index("id", unique=True)
    await db["users"].create_index("email", unique=True)
    await db["users"].create_index("roles")  # multikey

    # Skill ledgers — one per candidate
    await db["skill_ledgers"].create_index("candidateId", unique=True)

    # Assessments + coupons
    await db["assessments"].create_index("id", unique=True)
    await db["assessments"].create_index("slug")
    await db["assessments"].create_index("published")
    await db["coupons"].create_index("code", unique=True)

    # Verifier console
    await db["pending_reports"].create_index("id", unique=True)
    await db["session_reports"].create_index("id", unique=True)
    await db["verifier_slots"].create_index("id", unique=True)

    # Candidate portal
    await db["skill_reports"].create_index("id", unique=True)
    await db["skill_report_details"].create_index("id", unique=True)
    await db["insights"].create_index("id", unique=True)
    await db["public_profiles"].create_index("userId", unique=True)
    await db["session_history"].create_index("id", unique=True)
    await db["notifications"].create_index("id", unique=True)

    # Privacy / dossier / booking
    await db["privacy_settings"].create_index("userId", unique=True)
    await db["dossiers"].create_index("id", unique=True)
    await db["booking_catalogs"].create_index("catalogId", unique=True)
    await db["live_sessions"].create_index("id", unique=True)
    await db["my_interviews"].create_index("id", unique=True)

    log.info("Mongo indexes ensured.")
