"""Candidate-portal seed data.

Mirrors candidateExtras.ts, skillReportDetails.ts, notifications.ts.
Compact literals — content matches the frontend mock byte-for-byte where
the UI asserts on it.
"""

from app.db.mongo import get_database

SKILL_REPORTS: list[dict] = [
    {"id": "SVR-KAF-88421", "skill": "Kafka & Event Streams", "verifier": "D. Krishnan", "score": 76, "date": "Apr 26", "status": "published", "companiesViewed": 3},
    {"id": "SVR-SYS-72110", "skill": "System Design", "verifier": "M. Patel", "score": 82, "date": "Feb 02", "status": "published", "companiesViewed": 5},
    {"id": "SVR-NET-65433", "skill": ".NET Microservices", "verifier": "S. Mehra", "score": 87, "date": "Mar 14", "status": "published", "companiesViewed": 4},
    {"id": "SVR-PG-51200", "skill": "Postgres & Indexing", "verifier": "R. Kapoor", "score": 78, "date": "Jan 18", "status": "published", "companiesViewed": 2},
    {"id": "SVR-DS-44918", "skill": "Distributed Systems", "verifier": "D. Krishnan", "score": 64, "date": "Feb 02", "status": "published", "companiesViewed": 1},
]

_AARAV = {"name": "Aarav Rao", "id": "ANV-2481"}

SKILL_REPORT_DETAILS: list[dict] = [
    {
        "id": "SVR-KAF-88421",
        "skillId": "skl_005",
        "assessmentTitle": "Kafka & Event Streams",
        "candidate": _AARAV,
        "verifier": {"name": "Deepa Krishnan", "id": "VRF-042", "title": "Senior Kafka Practitioner · 9 yrs", "rating": "4.9"},
        "date": "April 26, 2026",
        "duration": "60 minutes",
        "type": "live",
        "score": 76,
        "depth": "Intermediate → Advanced",
        "verdict": "Strong mental model. Weaker on operational edge-cases.",
        "verdictLong": "Aarav demonstrates clear, production-grounded understanding of Kafka's core primitives — partitioning, consumer groups, and transactional producers. He reasoned through a whiteboard scenario with confidence and unprompted offered an insightful incident narrative about read_committed vs read_uncommitted. The gap is in broker internals — specifically producer-epoch fencing during consumer rebalance, where his answer was correct in direction but uncertain in mechanism.",
        "fitSignals": [
            {"area": "Event-driven systems", "signal": "Strong", "color": "var(--verdant)"},
            {"area": "High-throughput operations", "signal": "Emerging", "color": "var(--ochre)"},
            {"area": "Platform engineering", "signal": "Not probed", "color": "var(--ink-3)"},
        ],
        "rubric": [
            {"id": "r1", "dim": "Depth of understanding", "score": 82},
            {"id": "r2", "dim": "Operational realism", "score": 62},
            {"id": "r3", "dim": "Tradeoff reasoning", "score": 84},
            {"id": "r4", "dim": "Evidence from experience", "score": 78},
            {"id": "r5", "dim": "Clarity of explanation", "score": 88},
            {"id": "r6", "dim": "Edge-case handling", "score": 58},
        ],
        "phases": [
            {"num": "01", "title": "Warm-up & context", "done": True, "summary": "Candidate described experience at scale — 3M events/sec at previous role. Verifier noted claim for follow-up."},
            {"num": "02", "title": "Production scale", "done": True, "summary": "Discussed consumer group design decisions. Solid understanding of partition-consumer mapping."},
            {"num": "03", "title": "Partitioning deep-dive", "done": True, "summary": "Whiteboard exercise: partition key strategy, per-user ordering, global order tradeoffs. Demonstrated correctly."},
            {"num": "04", "title": "Exactly-once semantics", "done": True, "summary": "Explained transactional producers and read-committed semantics. Gap: uncertain on epoch fencing mechanism."},
            {"num": "05", "title": "Retrospective", "done": True, "summary": "Candidate volunteered a production incident around consumer isolation. Strong unprompted insight."},
        ],
        "summary": [
            "Partitioning strategy (user_id as key for per-user ordering)",
            "Consumer group semantics and rebalancing concepts",
            "Transactional producers and read-committed consumers",
            "Schema registry hygiene basics",
            "Production incident: read_committed isolation for retry consumer",
        ],
        "gaps": [
            {"id": "gp1", "area": "Producer epoch fencing", "evidence": 'Uncertain mechanism — "I think the broker fences the old epoch but I\'m not 100% sure." · 00:23:10', "severity": "medium"},
            {"id": "gp2", "area": "Consumer lag mitigation strategies", "evidence": 'Named no specific primitives beyond "add partitions" · 00:38:22', "severity": "low"},
            {"id": "gp3", "area": "Backpressure design patterns", "evidence": "Could not name upstream pressure primitives · 00:44:01", "severity": "low"},
        ],
        "gray": [
            {"id": "gr1", "area": "Kafka Streams & KSQL", "companies": 4},
            {"id": "gr2", "area": "Cross-region replication", "companies": 3},
            {"id": "gr3", "area": "Tiered storage operations", "companies": 2},
            {"id": "gr4", "area": "Stream-table duality (deep)", "companies": 4},
        ],
        "evidence": [
            {"id": "ev1", "t": "00:22:11", "type": "claim", "speaker": "AARAV", "text": "Partition key = user_id preserves per-user ordering. Across users, global order is lost.", "verdict": "Correct · demonstrated with whiteboard", "verdictColor": "var(--verdant)"},
            {"id": "ev2", "t": "00:23:10", "type": "hesitation", "speaker": "AARAV", "text": "…I think the broker fences the old producer epoch but I'm not 100% sure of the mechanism.", "verdict": "Gap identified — epoch fencing", "verdictColor": "var(--ochre)"},
            {"id": "ev3", "t": "00:45:32", "type": "insight", "speaker": "AARAV", "text": "In our incident, we moved read_committed to the retry consumer only, kept read_uncommitted for live dashboard.", "verdict": "Strong unprompted operational judgement", "verdictColor": "var(--verdant)"},
            {"id": "ev4", "t": "00:18:42", "type": "claim", "speaker": "AARAV", "text": "We were handling around 3 million events per second at peak on our payments pipeline.", "verdict": "Claim logged — architecture not probed", "verdictColor": "var(--ink-3)"},
            {"id": "ev5", "t": "00:52:10", "type": "claim", "speaker": "AARAV", "text": "Schema backward compatibility is the default we enforce — consumers always read older schemas fine.", "verdict": "Correct — adequately explained", "verdictColor": "var(--verdant)"},
        ],
    },
    {
        "id": "SVR-NET-65433",
        "skillId": "skl_001",
        "assessmentTitle": ".NET Microservices",
        "candidate": _AARAV,
        "verifier": {"name": "S. Mehra", "id": "VRF-018", "title": "Principal .NET Architect · 12 yrs", "rating": "4.9"},
        "date": "March 14, 2026",
        "duration": "60 minutes",
        "type": "bot-assisted",
        "score": 87,
        "depth": "Advanced",
        "verdict": "Confident architect-level grasp; service mesh details slightly thin.",
        "verdictLong": "Aarav showed advanced fluency in .NET service decomposition, dependency injection lifecycles, and resilience patterns (Polly, circuit breakers, retry policies). He reasoned through a non-trivial CQRS / event-sourcing tradeoff scenario cleanly. The only soft area was deep service-mesh primitives (Istio policy hierarchy) — answer was directionally correct but lacked specifics.",
        "fitSignals": [
            {"area": ".NET platform engineering", "signal": "Strong", "color": "var(--verdant)"},
            {"area": "CQRS / event sourcing", "signal": "Strong", "color": "var(--verdant)"},
            {"area": "Service mesh advanced", "signal": "Emerging", "color": "var(--ochre)"},
        ],
        "rubric": [
            {"id": "r1", "dim": "Service decomposition", "score": 91},
            {"id": "r2", "dim": "DI & lifecycle", "score": 88},
            {"id": "r3", "dim": "Resilience & retries", "score": 92},
            {"id": "r4", "dim": "CQRS / event sourcing", "score": 86},
            {"id": "r5", "dim": "Service mesh awareness", "score": 72},
            {"id": "r6", "dim": "Production incident reasoning", "score": 90},
        ],
        "phases": [
            {"num": "01", "title": "Warm-up", "done": True, "summary": "Walked through current platform."},
            {"num": "02", "title": "Decomposition", "done": True, "summary": "Bounded contexts, anti-corruption layer."},
            {"num": "03", "title": "Resilience", "done": True, "summary": "Polly policies, bulkhead patterns."},
            {"num": "04", "title": "CQRS scenario", "done": True, "summary": "Whiteboarded event-sourced order pipeline."},
            {"num": "05", "title": "Service mesh", "done": True, "summary": "Discussed mTLS, mesh observability."},
        ],
        "summary": [
            "Service decomposition with bounded contexts",
            "DI scopes and lifecycle correctness",
            "Polly retry / circuit-breaker policies",
            "Event-sourced order pipeline design",
            "Bulkhead isolation for noisy tenants",
        ],
        "gaps": [
            {"id": "gp1", "area": "Istio policy hierarchy", "evidence": "Generic answer about VirtualService vs DestinationRule precedence · 00:48:10", "severity": "low"},
        ],
        "gray": [
            {"id": "gr1", "area": "gRPC streaming", "companies": 2},
            {"id": "gr2", "area": "Linkerd specifics", "companies": 1},
        ],
        "evidence": [
            {"id": "ev1", "t": "00:14:20", "type": "insight", "speaker": "AARAV", "text": "We moved from a noisy-tenant problem to bulkheads with per-tenant connection pools. Cut p99 by 40%.", "verdict": "Strong unprompted operational story", "verdictColor": "var(--verdant)"},
            {"id": "ev2", "t": "00:48:10", "type": "hesitation", "speaker": "AARAV", "text": "I think VirtualService takes precedence over DestinationRule but I'd double-check the docs.", "verdict": "Gap identified — mesh policy hierarchy", "verdictColor": "var(--ochre)"},
        ],
    },
    {
        "id": "SVR-SYS-72110",
        "skillId": "skl_002",
        "assessmentTitle": "System Design",
        "candidate": _AARAV,
        "verifier": {"name": "M. Patel", "id": "VRF-022", "title": "Staff Engineer · Payments · 11 yrs", "rating": "4.8"},
        "date": "February 2, 2026",
        "duration": "90 minutes",
        "type": "live",
        "score": 82,
        "depth": "Advanced",
        "verdict": "Solid tradeoff reasoning; back-of-envelope sometimes optimistic.",
        "verdictLong": "Aarav navigated a payments-ledger design with clarity. He named consistency tradeoffs precisely (single-leader vs Raft quorum) and reasoned about idempotency keys at the PSP boundary. One soft area: his initial throughput estimate was off by ~2× and he needed prompting to revise.",
        "fitSignals": [
            {"area": "Payments domain", "signal": "Strong", "color": "var(--verdant)"},
            {"area": "Capacity planning", "signal": "Emerging", "color": "var(--ochre)"},
            {"area": "Multi-region", "signal": "Strong", "color": "var(--verdant)"},
        ],
        "rubric": [
            {"id": "r1", "dim": "Problem framing", "score": 88},
            {"id": "r2", "dim": "API design", "score": 82},
            {"id": "r3", "dim": "Storage tradeoffs", "score": 84},
            {"id": "r4", "dim": "Consistency reasoning", "score": 86},
            {"id": "r5", "dim": "Back-of-envelope", "score": 70},
            {"id": "r6", "dim": "Failure modes", "score": 82},
        ],
        "phases": [
            {"num": "01", "title": "Problem framing", "done": True, "summary": "Clarified scope, SLOs, scale."},
            {"num": "02", "title": "API & data model", "done": True, "summary": "Idempotent POST /charge, ledger schema."},
            {"num": "03", "title": "Storage", "done": True, "summary": "Postgres single-leader vs Raft quorum tradeoff."},
            {"num": "04", "title": "Consistency", "done": True, "summary": "Reconciliation pipeline & dual-write avoidance."},
            {"num": "05", "title": "Failure modes", "done": True, "summary": "PSP timeout, refund race conditions."},
        ],
        "summary": [
            "Idempotency keys scoped to PSP request",
            "Single-leader Postgres with logical replicas",
            "Reconciliation pipeline avoids dual-write",
            "Refund race conditions handled with state machine",
        ],
        "gaps": [
            {"id": "gp1", "area": "Throughput estimation", "evidence": "Initial estimate ~2× off; revised after prompt · 00:31:40", "severity": "low"},
        ],
        "gray": [
            {"id": "gr1", "area": "PCI scope boundaries", "companies": 3},
            {"id": "gr2", "area": "Tokenization vault internals", "companies": 2},
        ],
        "evidence": [
            {"id": "ev1", "t": "00:24:05", "type": "claim", "speaker": "AARAV", "text": "Idempotency key should be scoped to the PSP request, not the user — otherwise legitimate retries fail.", "verdict": "Correct · industry-standard reasoning", "verdictColor": "var(--verdant)"},
            {"id": "ev2", "t": "00:31:40", "type": "hesitation", "speaker": "AARAV", "text": "So that's… maybe 50K TPS sustained. Actually, let me redo that — closer to 25K.", "verdict": "Self-corrected after prompt", "verdictColor": "var(--ochre)"},
        ],
    },
    {
        "id": "SVR-DS-44918",
        "skillId": "skl_003",
        "assessmentTitle": "Distributed Systems",
        "candidate": _AARAV,
        "verifier": {"name": "D. Krishnan", "id": "VRF-042", "title": "Senior Distributed Systems · 9 yrs", "rating": "4.9"},
        "date": "February 2, 2026",
        "duration": "60 minutes",
        "type": "live",
        "score": 64,
        "depth": "Intermediate",
        "verdict": "Partial — solid on basics, weak on consensus internals. Retake recommended.",
        "verdictLong": "Aarav explained the CAP tradeoff and described Raft at a high level, but stumbled on leader election edge cases (term overlap, pre-vote). His operational reasoning was sound — circuit breakers, retry budgets — but theoretical depth on consensus needs work.",
        "fitSignals": [
            {"area": "Consensus internals", "signal": "Emerging", "color": "var(--ochre)"},
            {"area": "Operational reasoning", "signal": "Strong", "color": "var(--verdant)"},
            {"area": "Failure modes", "signal": "Emerging", "color": "var(--ochre)"},
        ],
        "rubric": [
            {"id": "r1", "dim": "CAP & tradeoffs", "score": 78},
            {"id": "r2", "dim": "Consensus theory", "score": 52},
            {"id": "r3", "dim": "Leader election edges", "score": 48},
            {"id": "r4", "dim": "Operational reasoning", "score": 80},
            {"id": "r5", "dim": "Failure modes", "score": 64},
            {"id": "r6", "dim": "Time / ordering", "score": 62},
        ],
        "phases": [
            {"num": "01", "title": "CAP recap", "done": True, "summary": "Clean explanation of CAP tradeoffs."},
            {"num": "02", "title": "Raft basics", "done": True, "summary": "High-level Raft was solid."},
            {"num": "03", "title": "Leader election", "done": True, "summary": "Stumbled on term overlap."},
            {"num": "04", "title": "Failure modes", "done": True, "summary": "Network partition reasoning OK."},
            {"num": "05", "title": "Time & ordering", "done": True, "summary": "Lamport vs vector clocks confused."},
        ],
        "summary": [
            "CAP tradeoff explained clearly",
            "Raft at a high level",
            "Circuit breaker + retry budget patterns",
            "Network partition reasoning",
        ],
        "gaps": [
            {"id": "gp1", "area": "Raft pre-vote / term overlap", "evidence": "Could not describe pre-vote phase · 00:28:14", "severity": "high"},
            {"id": "gp2", "area": "Lamport vs vector clocks", "evidence": "Mixed up partial vs total ordering · 00:42:30", "severity": "medium"},
        ],
        "gray": [
            {"id": "gr1", "area": "CRDTs", "companies": 2},
            {"id": "gr2", "area": "Paxos variants", "companies": 1},
        ],
        "evidence": [
            {"id": "ev1", "t": "00:18:50", "type": "claim", "speaker": "AARAV", "text": "In AP mode, we accept inconsistency for availability — that's the explicit choice.", "verdict": "Correct framing", "verdictColor": "var(--verdant)"},
            {"id": "ev2", "t": "00:28:14", "type": "hesitation", "speaker": "AARAV", "text": "Pre-vote phase… I don't recall the exact purpose. It avoids unnecessary term bumps?", "verdict": "Gap — Raft pre-vote semantics", "verdictColor": "var(--ochre)"},
        ],
    },
    {
        "id": "SVR-PG-51200",
        "skillId": "skl_004",
        "assessmentTitle": "Postgres & Indexing",
        "candidate": _AARAV,
        "verifier": {"name": "R. Kapoor", "id": "VRF-031", "title": "Postgres internals · 10 yrs", "rating": "4.9"},
        "date": "January 18, 2026",
        "duration": "60 minutes",
        "type": "live",
        "score": 78,
        "depth": "Intermediate",
        "verdict": "Solid practitioner. Light on internals (buffer manager, MVCC GC).",
        "verdictLong": "Aarav reasoned through indexing strategies with confidence — partial, covering, expression indexes — and named the right tool for the right query. His weak spots are deeper internals like autovacuum dead-tuple thresholds and the buffer manager.",
        "fitSignals": [
            {"area": "Index strategy", "signal": "Strong", "color": "var(--verdant)"},
            {"area": "Query tuning", "signal": "Strong", "color": "var(--verdant)"},
            {"area": "Postgres internals", "signal": "Emerging", "color": "var(--ochre)"},
        ],
        "rubric": [
            {"id": "r1", "dim": "Index types & uses", "score": 88},
            {"id": "r2", "dim": "Query planner reading", "score": 82},
            {"id": "r3", "dim": "MVCC understanding", "score": 70},
            {"id": "r4", "dim": "Autovacuum tuning", "score": 64},
            {"id": "r5", "dim": "Partitioning strategies", "score": 80},
            {"id": "r6", "dim": "Replication topology", "score": 78},
        ],
        "phases": [
            {"num": "01", "title": "Workload framing", "done": True, "summary": "Read-heavy OLTP, ~12K QPS."},
            {"num": "02", "title": "Index strategy", "done": True, "summary": "Covering + partial indexes."},
            {"num": "03", "title": "Planner", "done": True, "summary": "Read EXPLAIN ANALYZE accurately."},
            {"num": "04", "title": "MVCC", "done": True, "summary": "Knew XID, weak on dead tuple GC."},
            {"num": "05", "title": "Partitioning", "done": True, "summary": "Range vs hash for time-series."},
        ],
        "summary": [
            "Partial + covering index combinations",
            "EXPLAIN ANALYZE reading",
            "Range vs hash partitioning for time-series",
            "Logical vs streaming replication tradeoffs",
        ],
        "gaps": [
            {"id": "gp1", "area": "Autovacuum thresholds", "evidence": "Did not know default scale factor or how to tune for hot tables · 00:38:00", "severity": "medium"},
        ],
        "gray": [
            {"id": "gr1", "area": "PgBouncer pool modes", "companies": 2},
            {"id": "gr2", "area": "Logical replication conflicts", "companies": 1},
        ],
        "evidence": [
            {"id": "ev1", "t": "00:21:08", "type": "insight", "speaker": "AARAV", "text": 'We use partial indexes on status="active" — cut the index size by 6× since 90% of rows are archived.', "verdict": "Strong production-grounded reasoning", "verdictColor": "var(--verdant)"},
            {"id": "ev2", "t": "00:38:00", "type": "hesitation", "speaker": "AARAV", "text": "Autovacuum threshold? I usually leave it on defaults and watch pg_stat_user_tables.", "verdict": "Gap — autovacuum tuning", "verdictColor": "var(--ochre)"},
        ],
    },
]

INSIGHTS: list[dict] = [
    {"id": "in_001", "kind": "follow-up", "title": "Kafka Streams Gray — 4 companies asked this week", "body": "A targeted 30-min follow-up on Kafka Streams would move it from Gray to Verified. NorthStack · Razorpay · Meesho · ZeroPay have all asked.", "cta": "Book follow-up", "companies": 4, "acted": False},
    {"id": "in_002", "kind": "gap", "title": "Producer-epoch fencing flagged in your last Kafka session", "body": "D. Krishnan flagged this as a Gap area. A 30-min retake on this specific topic would bump your Kafka score from 76 to ~82.", "cta": "Schedule retake", "acted": False},
    {"id": "in_003", "kind": "momentum", "title": "You’re in the top 12% for Backend roles", "body": "Based on your 4 verified skills and verification score of 78. Profile views from companies have grown 38% this month.", "cta": "Share public profile", "acted": False},
]

ONBOARDING_STEPS: list[dict] = [
    {"id": "s1", "title": "Confirm your background", "body": "Tell us about your years of experience, current role, and primary domains so we can suggest the right assessments.", "done": True},
    {"id": "s2", "title": "Claim your skills", "body": "Add the skills you’d like to verify. We’ll match each one to the right Live, Bot, or Bot-Assisted assessment.", "done": True},
    {"id": "s3", "title": "Book your first verification", "body": "Pick a slot with a senior verifier. Free for your first session. Takes 60 minutes.", "done": False},
    {"id": "s4", "title": "Share your dossier", "body": "When ready, share your dossier link with companies. They cannot see drafts — only published reports.", "done": False},
]

PUBLIC_PROFILES: list[dict] = [
    {
        "userId": "usr_cand_001",
        "shareUrl": "https://tatvo.app/p/aarav-rao",
        "anvId": "ANV-2481",
        "lastUpdated": "Apr 26, 2026",
        "headline": "Distributed systems engineer specialising in event-driven architectures and high-throughput data pipelines.",
        "views": 1248,
        "uniqueCompanies": 38,
        "inboundChats": 6,
        "about": "Backend engineer focused on .NET, distributed systems, and event-driven design. 6 years across fintech and SaaS. Based in Bengaluru.",
        "highlights": [
            {"id": "h1", "skill": "Kafka & Event Streams", "score": 76},
            {"id": "h2", "skill": ".NET Microservices", "score": 87},
            {"id": "h3", "skill": "System Design", "score": 82},
            {"id": "h4", "skill": "Postgres & Indexing", "score": 78},
        ],
        "constellation": [
            {"name": ".NET Microservices", "score": 87, "state": "verified"},
            {"name": "System Design", "score": 82, "state": "verified"},
            {"name": "Kafka & Event Streams", "score": 76, "state": "verified"},
            {"name": "Postgres & Indexing", "score": 78, "state": "verified"},
            {"name": "Distributed Systems", "score": 64, "state": "partial"},
            {"name": "Kafka Streams", "score": 0, "state": "gray"},
            {"name": "Payments Domain", "score": 0, "state": "gray"},
            {"name": "gRPC & Protobuf", "score": 0, "state": "gray"},
        ],
        "timeline": [
            {"id": "tl1", "date": "Jan 18", "skill": "Postgres & Indexing", "score": 78, "type": "live"},
            {"id": "tl2", "date": "Feb 02", "skill": "System Design", "score": 82, "type": "live"},
            {"id": "tl3", "date": "Feb 02", "skill": "Distributed Systems", "score": 52, "type": "live", "note": "First attempt"},
            {"id": "tl4", "date": "Feb 28", "skill": "Distributed Systems", "score": 64, "type": "live", "note": "Retake · +12"},
            {"id": "tl5", "date": "Mar 14", "skill": ".NET Microservices", "score": 87, "type": "bot-assisted"},
            {"id": "tl6", "date": "Apr 26", "skill": "Kafka & Event Streams", "score": 76, "type": "live"},
        ],
        "grayAreas": [
            {"id": "g1", "name": "Kafka Streams", "companies": 4},
            {"id": "g2", "name": "Payments Domain", "companies": 3},
            {"id": "g3", "name": "gRPC & Protobuf", "companies": 2},
            {"id": "g4", "name": "Cross-region replication", "companies": 3},
        ],
    },
    {
        "userId": "usr_ver_001",
        "shareUrl": "https://tatvo.app/p/maya-iyer",
        "anvId": "ANV-7104",
        "lastUpdated": "May 30, 2026",
        "headline": ".NET architect and system designer. 9 years across fintech and SaaS. Verifies on Tatvo.",
        "views": 3104,
        "uniqueCompanies": 76,
        "inboundChats": 14,
        "about": "Staff engineer at a fintech with deep experience in payments, .NET microservices, and large-scale system design. Active Tatvo interviewer for .NET Microservices and System Design.",
        "highlights": [
            {"id": "h1", "skill": ".NET Microservices", "score": 91},
            {"id": "h2", "skill": "System Design", "score": 88},
            {"id": "h3", "skill": "Postgres & Indexing", "score": 82},
        ],
        "constellation": [
            {"name": ".NET Microservices", "score": 91, "state": "verified"},
            {"name": "System Design", "score": 88, "state": "verified"},
            {"name": "Postgres & Indexing", "score": 82, "state": "verified"},
            {"name": "React / Next.js", "score": 0, "state": "gray"},
            {"name": "Kubernetes", "score": 0, "state": "gray"},
        ],
        "timeline": [
            {"id": "tl1", "date": "Jul 18", "skill": "Postgres & Indexing", "score": 82, "type": "live"},
            {"id": "tl2", "date": "Aug 02", "skill": "System Design", "score": 88, "type": "live"},
            {"id": "tl3", "date": "Sep 14", "skill": ".NET Microservices", "score": 91, "type": "live"},
            {"id": "tl4", "date": "Nov 12", "skill": "Promoted to freelance interviewer", "score": 0, "type": "live", "note": ".NET + System Design authority granted"},
        ],
        "grayAreas": [
            {"id": "g1", "name": "React / Next.js", "companies": 2},
            {"id": "g2", "name": "Kubernetes", "companies": 3},
        ],
    },
    {
        "userId": "usr_spec_001",
        "shareUrl": "https://tatvo.app/p/suresh-mehra",
        "anvId": "ANV-8801",
        "lastUpdated": "Apr 26, 2026",
        "headline": "Principal architect · 18 years across payments and infra. Invited specialist on Tatvo.",
        "views": 1842,
        "uniqueCompanies": 41,
        "inboundChats": 9,
        "about": "Tatvo-invited specialist. Suresh joined as an industry authority and was not assessed by the platform — his verifier authority is established by his external record.",
        "highlights": [],
        "constellation": [],
        "timeline": [],
        "grayAreas": [],
    },
]

SESSION_HISTORY: list[dict] = [
    {"id": "SVR-KAF-88421", "skill": "Kafka & Event Streams", "date": "Apr 26, 2026", "duration": "60 min", "verifier": "D. Krishnan", "score": 76, "status": "published"},
    {"id": "SVR-NET-65433", "skill": ".NET Microservices", "date": "Mar 14, 2026", "duration": "60 min", "verifier": "S. Mehra", "score": 87, "status": "published"},
    {"id": "SVR-SYS-72110", "skill": "System Design", "date": "Feb 02, 2026", "duration": "90 min", "verifier": "M. Patel", "score": 82, "status": "published"},
    {"id": "SVR-DS-44918", "skill": "Distributed Systems (Retake)", "date": "Feb 02, 2026", "duration": "60 min", "verifier": "D. Krishnan", "score": 64, "status": "published"},
    {"id": "SVR-PG-51200", "skill": "Postgres & Indexing", "date": "Jan 18, 2026", "duration": "60 min", "verifier": "R. Kapoor", "score": 78, "status": "published"},
    {"id": "SVR-DS-31001", "skill": "Distributed Systems", "date": "Nov 20, 2025", "duration": "60 min", "verifier": "D. Krishnan", "score": 52, "status": "archived", "note": "Retaken Feb 02"},
]

NOTIFICATIONS: list[dict] = [
    {"id": "n_001", "kind": "session", "title": "Live session in 1h", "body": "Kafka & Event Streams with D. Krishnan starts at 10:30 IST.", "createdAt": "2026-04-26T09:30:00.000Z", "read": False, "href": "/candidate/session/KAF-88421"},
    {"id": "n_002", "kind": "dossier", "title": "Dossier published", "body": "Your Kafka dossier is ready. Score 76/100 — solid, advanced.", "createdAt": "2026-04-26T12:00:00.000Z", "read": False, "href": "/candidate/dossier"},
    {"id": "n_003", "kind": "followup", "title": "Follow-up requested", "body": "NorthStack asked for a 30-min Payments idempotency follow-up.", "createdAt": "2026-04-27T08:15:00.000Z", "read": False, "href": "/candidate/booking"},
    {"id": "n_004", "kind": "company", "title": "4 companies viewed your dossier", "body": "Stripe, NorthStack, TechCorp India, ZeroPay — past 7 days.", "createdAt": "2026-04-25T10:00:00.000Z", "read": True},
    {"id": "n_005", "kind": "integrity", "title": "Identity verification complete", "body": "Your account passed all integrity checks.", "createdAt": "2026-04-20T16:30:00.000Z", "read": True},
]


async def seed_candidate() -> int:
    db = get_database()
    inserted = 0

    async def _fill(coll_name: str, items: list[dict], key: str = "id") -> int:
        coll = db[coll_name]
        n = 0
        for item in items:
            if not await coll.find_one({key: item[key]}):
                await coll.insert_one(dict(item))
                n += 1
        return n

    inserted += await _fill("skill_reports", SKILL_REPORTS)
    inserted += await _fill("skill_report_details", SKILL_REPORT_DETAILS)
    inserted += await _fill("insights", INSIGHTS)
    inserted += await _fill("onboarding_steps", ONBOARDING_STEPS)
    inserted += await _fill("public_profiles", PUBLIC_PROFILES, key="userId")
    inserted += await _fill("session_history", SESSION_HISTORY)
    inserted += await _fill("notifications", NOTIFICATIONS)
    return inserted
