r"""One-shot seeder: populate real data into Postgres without waiting for a
backend restart. Runs every registered seeder (idempotent upserts) and then
inserts a couple of report-LESS assessment transcripts (status "ended",
dossier=None) so the live-assessment pipeline's starting artifact exists but
no report/dossier has been generated yet.

Run:  .\.venv\Scripts\python.exe run_seed_once.py
"""

import asyncio
import selectors
import sys


async def _seed_users_email_safe(db) -> int:
    """Like app.db.seed.seed_users, but skips a template when EITHER its id
    OR its email already exists — the two real Google accounts are already
    in `users` (created by real logins under different ids), and the stock
    seeder only checks by id, so it collides on the unique email."""
    from app.core.timefmt import parse_wire
    from app.db.seed import SEED_USERS
    from app.repositories.user_repo import UserRepository

    repo = UserRepository(db)
    inserted = 0
    for template in SEED_USERS:
        if await repo.find_by_id(template["id"]):
            continue
        if await repo.find_by_email(template["email"]):
            continue
        fields = {k: v for k, v in template.items() if k != "roles"}
        fields["created_at"] = parse_wire(fields["created_at"])
        await repo.insert_with_roles(roles=template["roles"], **fields)
        inserted += 1
    return inserted


async def _run_seeds_email_safe(db) -> None:
    """Mirror of app.db.seed.run_seeds, but with email-safe user seeding."""
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

    await _seed_users_email_safe(db)
    await seed_simple_bots(db)
    await seed_agent_registry(db)
    await seed_skill_ledgers(db)
    await seed_assessments(db)
    await seed_coupons(db)
    await seed_candidate(db)
    await seed_verifier(db)
    await seed_portal(db)
    await seed_approvals(db)
    await seed_company(db)
    await seed_admin_ops(db)
    await seed_metrics(db)


async def _main() -> None:
    from app.db.session import connect_to_db, close_db, get_sessionmaker
    from app.models.session_ingest import AssessmentTranscript

    await connect_to_db()
    try:
        async with get_sessionmaker()() as db:
            # 1) Baseline real data (users, bots, agents, assessments/catalogs,
            #    candidate, verifier, portal, approvals, company, admin-ops
            #    snapshot, metrics).
            await _run_seeds_email_safe(db)

            # 2) Report-less transcripts. One finished RAW live-assessment per
            #    row: full transcript lines present, status "ended", dossier
            #    None -> the report has deliberately NOT been generated yet.
            transcripts = [
                {
                    "id": "KAF-98001",
                    "room": "KAF-98001",
                    "booking_id": "int_001",
                    "bot_id": "BOT-001",
                    "response_mode": "voice",
                    "duration_ms": 58 * 60 * 1000,
                    "transcript": [
                        {"t": 0, "who": "bot", "text": "Welcome. Today we'll go deep on Kafka and event streaming. Ready to start?"},
                        {"t": 8, "who": "candidate", "text": "Yes, ready."},
                        {"t": 14, "who": "bot", "text": "Walk me through what happens when a producer sends a record to a topic with 6 partitions and no explicit key."},
                        {"t": 32, "who": "candidate", "text": "With no key the partitioner spreads records round-robin (sticky batching per batch) across the 6 partitions, so ordering is only guaranteed per-partition, not across the topic."},
                        {"t": 70, "who": "bot", "text": "Good. Now the consumer side — you have a consumer group of 4 consumers on those 6 partitions. Describe the assignment and what happens when a 5th consumer joins."},
                        {"t": 96, "who": "candidate", "text": "Two consumers get 2 partitions, two get 1 — range or cooperative-sticky assignor decides. A 5th joining triggers a rebalance; with cooperative-sticky only the moved partitions are revoked, not the whole group."},
                        {"t": 150, "who": "bot", "text": "How would you guarantee exactly-once from a Kafka topic, through processing, back to another Kafka topic?"},
                        {"t": 176, "who": "candidate", "text": "Transactional producer with enable.idempotence, read-process-write inside a transaction, consumer isolation.level=read_committed, and commit offsets via sendOffsetsToTransaction so the offset commit and output are atomic."},
                        {"t": 240, "who": "bot", "text": "Last one — a partition's consumer lag is climbing steadily under constant load. How do you diagnose it?"},
                        {"t": 262, "who": "candidate", "text": "Check if one partition is hot (keyed skew), compare per-partition lag, look at consumer processing time vs poll interval, GC pauses, and whether max.poll.records is too high causing rebalances. Then scale partitions/consumers or fix the key distribution."},
                        {"t": 330, "who": "bot", "text": "Thanks — that's the end of the session."},
                    ],
                    "participants": [
                        {"identity": "usr_cand_001", "name": "Aarav Rao", "role": "candidate"},
                        {"identity": "BOT-001", "name": "Bob", "role": "bot"},
                    ],
                    "extra_metadata": {"skill": "Kafka & Event Streams", "catalog_id": "KAF-204", "depth": "Senior"},
                },
                {
                    "id": "DOT-98002",
                    "room": "DOT-98002",
                    "booking_id": "int_002",
                    "bot_id": "BOT-002",
                    "response_mode": "text",
                    "duration_ms": 47 * 60 * 1000,
                    "transcript": [
                        {"t": 0, "who": "bot", "text": "We'll cover .NET microservices today. First: how do you handle a distributed transaction across two services without 2PC?"},
                        {"t": 20, "who": "candidate", "text": "Saga pattern — either orchestration with a central coordinator or choreography via events. Each step has a compensating action to roll back on failure."},
                        {"t": 70, "who": "bot", "text": "In ASP.NET Core, how do you propagate a correlation id across service calls for tracing?"},
                        {"t": 92, "who": "candidate", "text": "Middleware reads/creates the correlation id header, pushes it into a logging scope, and an outgoing HttpClient DelegatingHandler re-attaches it. W3C traceparent via OpenTelemetry does this automatically."},
                        {"t": 150, "who": "bot", "text": "How would you implement idempotent message handling for an at-least-once broker?"},
                        {"t": 172, "who": "candidate", "text": "Dedup table keyed by message id with a unique constraint, or an inbox pattern — record processed ids transactionally with the side effect so a replay is a no-op."},
                        {"t": 230, "who": "bot", "text": "Good. That's everything — thanks."},
                    ],
                    "participants": [
                        {"identity": "usr_cand_001", "name": "Aarav Rao", "role": "candidate"},
                        {"identity": "BOT-002", "name": "Dot", "role": "bot"},
                    ],
                    "extra_metadata": {"skill": ".NET Microservices", "catalog_id": "DOT-101", "depth": "Senior"},
                },
            ]

            inserted_t = 0
            for t in transcripts:
                if await db.get(AssessmentTranscript, t["id"]):
                    continue
                db.add(
                    AssessmentTranscript(
                        id=t["id"],
                        room=t["room"],
                        booking_id=t["booking_id"],
                        bot_id=t["bot_id"],
                        response_mode=t["response_mode"],
                        status="ended",  # report NOT generated yet
                        duration_ms=t["duration_ms"],
                        turn_count=len(t["transcript"]),
                        transcript=t["transcript"],
                        participants=t["participants"],
                        extra_metadata=t["extra_metadata"],
                        dossier=None,  # no report
                    )
                )
                inserted_t += 1

            await db.commit()
            print(f"Seed complete. Transcripts inserted: {inserted_t}")
    finally:
        await close_db()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_main())
