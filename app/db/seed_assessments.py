"""Assessment + coupon seed data — mirror of assessmentsFull.ts + coupons.ts."""

from app.db.mongo import get_database

SEED_ASSESSMENTS: list[dict] = [
    {
        "id": "ASS-001",
        "slug": "kafka-event-streams",
        "title": "Kafka & Event Streams",
        "domain": "Backend",
        "depth": "Advanced",
        "type": "live",
        "duration": 60,
        "price": 0,
        "available": 4,
        "popular": True,
        "published": True,
        "description": "Production-grade event-streaming. Real incidents, partitioning strategy, exactly-once semantics, schema evolution. No textbook questions.",
        "tags": ["Kafka", "Event-driven", "Streaming", "Distributed"],
        "probes": ["Partitioning & ordering", "Consumer group semantics", "Exactly-once delivery", "Operational incidents"],
        "botIds": ["BOT-003"],
        "sessions": 203,
    },
    {
        "id": "ASS-002",
        "slug": "system-design",
        "title": "System Design · Scalable Systems",
        "domain": "Backend",
        "depth": "Advanced",
        "type": "live",
        "duration": 90,
        "price": 0,
        "available": 6,
        "popular": True,
        "published": True,
        "description": "Design a system end-to-end: capacity estimation, data modeling, bottleneck analysis, tradeoffs. Verifier plays a senior engineer asking hard follow-ups.",
        "tags": ["System Design", "Scalability", "Architecture", "Databases"],
        "probes": ["Capacity & estimation", "Data model decisions", "Read/write bottlenecks", "Failure modes"],
        "botIds": [],
        "sessions": 412,
    },
    {
        "id": "ASS-003",
        "slug": "dotnet-microservices",
        "title": ".NET Microservices",
        "domain": "Backend",
        "depth": "Advanced",
        "type": "bot-assisted",
        "duration": 60,
        "price": 0,
        "available": 3,
        "popular": False,
        "published": True,
        "description": "Real-world .NET service design: DI, resilience patterns, CQRS, inter-service communication. AI-led session reviewed by a specialist verifier.",
        "tags": [".NET", "Microservices", "C#", "CQRS", "Resilience"],
        "probes": ["Service decomposition", "DI & lifecycle", "Resilience & retries", "CQRS / event sourcing"],
        "botIds": ["BOT-001"],
        "sessions": 142,
    },
    {
        "id": "ASS-004",
        "slug": "postgres-internals",
        "title": "Postgres Internals & Tuning",
        "domain": "Data",
        "depth": "Intermediate",
        "type": "bot",
        "duration": 60,
        "price": 0,
        "available": 999,
        "popular": False,
        "published": True,
        "description": "Query planning, indexing strategy, MVCC, vacuuming, replication. Fully automated AI assessment — instant report after completion.",
        "tags": ["Postgres", "Indexing", "Query planning", "MVCC"],
        "probes": ["Index types & selection", "EXPLAIN ANALYZE", "MVCC & locking", "Replication lag"],
        "botIds": ["BOT-004"],
        "sessions": 87,
    },
    {
        "id": "ASS-005",
        "slug": "distributed-systems",
        "title": "Distributed Systems Fundamentals",
        "domain": "Backend",
        "depth": "Intermediate",
        "type": "bot-assisted",
        "duration": 60,
        "price": 0,
        "available": 4,
        "popular": False,
        "published": True,
        "description": "CAP theorem in practice, consistency models, consensus, failure detection. AI leads, human verifier reviews and signs off the report.",
        "tags": ["Distributed Systems", "CAP", "Raft", "Consistency"],
        "probes": ["Consistency models", "Leader election", "Clock & ordering", "Partition tolerance"],
        "botIds": ["BOT-001"],
        "sessions": 38,
    },
    {
        "id": "ASS-006",
        "slug": "payment-idempotency",
        "title": "Payments & Idempotency",
        "domain": "Payments",
        "depth": "Advanced",
        "type": "live",
        "duration": 60,
        "price": 1499,
        "available": 2,
        "popular": True,
        "published": True,
        "description": "PSP integrations, idempotency at the API boundary, double-charge prevention, refund and dispute flows. Built for fintech engineers.",
        "tags": ["Payments", "Idempotency", "PSP", "Fintech"],
        "probes": ["Idempotency key design", "Refund race conditions", "Chargeback flows", "PCI scope"],
        "botIds": ["BOT-005"],
        "sessions": 54,
    },
    {
        "id": "ASS-007",
        "slug": "react-architecture",
        "title": "React · Frontend Architecture",
        "domain": "Frontend",
        "depth": "Intermediate",
        "type": "bot",
        "duration": 60,
        "price": 0,
        "available": 999,
        "popular": False,
        "published": True,
        "description": "State management decisions, rendering strategies, code splitting, performance profiling. Instant AI assessment — results within minutes.",
        "tags": ["React", "Next.js", "State management", "Performance"],
        "probes": ["Rendering & hydration", "State architecture", "Bundle & code split", "Core Web Vitals"],
        "botIds": ["BOT-006"],
        "sessions": 76,
    },
    {
        "id": "ASS-008",
        "slug": "aws-architecture",
        "title": "AWS Cloud Architecture",
        "domain": "Cloud",
        "depth": "Intermediate",
        "type": "bot-assisted",
        "duration": 60,
        "price": 999,
        "available": 4,
        "popular": False,
        "published": False,
        "description": "Compute, storage, networking, cost optimization, IAM, observability on AWS. AI-led session with human sign-off.",
        "tags": ["AWS", "Cloud", "IAM", "Cost optimization"],
        "probes": ["Compute selection", "Storage tiers", "IAM policy", "Cost optimization"],
        "botIds": [],
        "sessions": 0,
    },
]

SEED_COUPONS: list[dict] = [
    {"code": "LAUNCH50", "type": "percent", "value": 50, "desc": "50% off — launch offer", "active": True},
    {"code": "FREE100", "type": "fixed", "value": 99999, "desc": "Full discount", "active": True},
    {"code": "FIRST20", "type": "percent", "value": 20, "desc": "20% off — first booking", "active": True},
    {"code": "STRIPE200", "type": "fixed", "value": 200, "desc": "₹200 off — Stripe partnership", "active": False},
]


async def seed_assessments() -> int:
    db = get_database()
    coll = db["assessments"]
    inserted = 0
    for template in SEED_ASSESSMENTS:
        if await coll.find_one({"id": template["id"]}):
            continue
        await coll.insert_one(dict(template))
        inserted += 1
    return inserted


async def seed_coupons() -> int:
    db = get_database()
    coll = db["coupons"]
    inserted = 0
    for template in SEED_COUPONS:
        if await coll.find_one({"code": template["code"]}):
            continue
        await coll.insert_one(dict(template))
        inserted += 1
    return inserted
