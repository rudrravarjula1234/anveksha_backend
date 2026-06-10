"""Verifier seed data — mirror of verifier.ts + verifierOps.ts.

Singletons (queue, brief, governance, earnings, profile) are stored as
one document each with `key: "default"` — multi-verifier support later
swaps the key for the verifier's user id.
"""

from app.db.mongo import get_database

QUEUE: dict = {
    "key": "default",
    "stats": {"rating": 4.9, "sessionCount": 247, "reliability": 98, "earnings": 84200},
    "live": [
        {
            "id": "ses_l1",
            "rawId": "RAW-S-88421",
            "time": "Now",
            "date": "Today",
            "candidate": "Aarav Rao",
            "candidateInitials": "A",
            "skill": "Kafka & Event Streams",
            "duration": 60,
            "status": "live",
            "tags": ["High stakes", "3 companies watching"],
            "depth": "Intermediate → Advanced",
        }
    ],
    "upcoming": [
        {
            "id": "ses_u1",
            "rawId": "RAW-S-88422",
            "time": "14:00",
            "date": "Today",
            "candidate": "Priya Nair",
            "candidateInitials": "P",
            "skill": "System Design · Payments",
            "duration": 90,
            "status": "scheduled",
            "tags": ["Retake · delta only"],
            "depth": "Advanced",
        },
        {
            "id": "ses_u2",
            "rawId": "RAW-S-88423",
            "time": "16:30",
            "date": "Today",
            "candidate": "Omar Haddad",
            "candidateInitials": "O",
            "skill": ".NET Microservices",
            "duration": 60,
            "status": "scheduled",
            "tags": ["First verification"],
            "depth": "Intermediate",
        },
        {
            "id": "ses_u3",
            "rawId": "RAW-S-88424",
            "time": "Tomorrow 10:00",
            "date": "Tomorrow",
            "candidate": "Li Wei",
            "candidateInitials": "L",
            "skill": "Postgres Internals",
            "duration": 60,
            "status": "scheduled",
            "tags": ["Advanced track"],
            "depth": "Advanced",
        },
    ],
    "completed": [],
}

BRIEF: dict = {
    "key": "default",
    "sessionId": "ses_u1",
    "candidate": "Priya Nair",
    "skill": "Payments System Design",
    "summary": (
        "This is a retake. Focus the hour on last session’s Gap: idempotency in "
        "distributed payment flows. Skip general system design warm-up."
    ),
    "prioritizedProbes": [
        "Idempotency keys at PSP boundary",
        "Refund / dispute race conditions",
        "Double-charge recovery playbook",
    ],
    "grayRequested": ["Tokenization", "PCI scope", "Chargeback flows"],
}

PENDING_REPORTS: list[dict] = [
    {
        "id": "rpt_001",
        "sessionId": "ses_l1",
        "candidate": "Aarav Rao",
        "initials": "AR",
        "skill": "Kafka & Event Streams",
        "date": "Apr 26",
        "aiScore": 72,
    },
    {
        "id": "rpt_002",
        "sessionId": "ses_u2",
        "candidate": "Omar Haddad",
        "initials": "OH",
        "skill": ".NET Microservices",
        "date": "Apr 26",
        "aiScore": 68,
    },
]

REPORTS: list[dict] = [
    {
        "id": "rpt_001",
        "sessionId": "ses_l1",
        "candidateName": "Aarav Rao",
        "skill": "Kafka & Event Streams",
        "verdict": "verified",
        "overallScore": 76,
        "sections": [
            {"id": "sec_1", "title": "Depth of understanding", "aiScore": 82, "verifierScore": 82, "notes": "", "evidence": []},
            {"id": "sec_2", "title": "Operational realism", "aiScore": 62, "verifierScore": 62, "notes": "", "evidence": []},
            {"id": "sec_3", "title": "Tradeoff reasoning", "aiScore": 84, "verifierScore": 84, "notes": "", "evidence": []},
            {"id": "sec_4", "title": "Evidence from experience", "aiScore": 78, "verifierScore": 78, "notes": "", "evidence": []},
            {"id": "sec_5", "title": "Clarity of explanation", "aiScore": 88, "verifierScore": 88, "notes": "", "evidence": []},
            {"id": "sec_6", "title": "Edge-case handling", "aiScore": 58, "verifierScore": 58, "notes": "", "evidence": []},
        ],
        "grayAreas": ["Cross-region replication", "Kafka Streams / KSQL"],
        "strengths": ["Partitioning strategy", "Consumer group semantics"],
        "status": "review",
        "createdAt": "2026-04-26T11:30:00.000Z",
    },
    {
        "id": "rpt_002",
        "sessionId": "ses_u2",
        "candidateName": "Omar Haddad",
        "skill": ".NET Microservices",
        "verdict": "partial",
        "overallScore": 68,
        "sections": [
            {"id": "sec_1", "title": "Service decomposition", "aiScore": 74, "verifierScore": 74, "notes": "", "evidence": []},
            {"id": "sec_2", "title": "DI & lifecycle", "aiScore": 70, "verifierScore": 70, "notes": "", "evidence": []},
            {"id": "sec_3", "title": "Resilience & retries", "aiScore": 62, "verifierScore": 62, "notes": "", "evidence": []},
            {"id": "sec_4", "title": "CQRS / event sourcing", "aiScore": 58, "verifierScore": 58, "notes": "", "evidence": []},
            {"id": "sec_5", "title": "Service mesh awareness", "aiScore": 66, "verifierScore": 66, "notes": "", "evidence": []},
            {"id": "sec_6", "title": "Production incident reasoning", "aiScore": 72, "verifierScore": 72, "notes": "", "evidence": []},
        ],
        "grayAreas": ["Service mesh advanced", "gRPC streaming"],
        "strengths": ["CQRS patterns", "Resilience playbook"],
        "status": "review",
        "createdAt": "2026-04-26T15:20:00.000Z",
    },
]

SUGGESTED_GAPS: dict = {
    "key": "default",
    "gaps": [
        {"id": "g1", "text": "Producer epoch fencing", "sub": "Uncertain mechanism", "accepted": True},
        {"id": "g2", "text": "Consumer lag mitigation", "sub": "Textbook-only", "accepted": True},
        {
            "id": "g3",
            "text": "Schema compatibility rules",
            "sub": "Missed question",
            "accepted": False,
            "note": "Not asked in session — downgrade to Gray",
        },
    ],
}

GOVERNANCE: dict = {
    "key": "default",
    "reliability": 98,
    "scoreVariance": 4.2,
    "candidateRating": 4.9,
    "appealRate": 1.2,
    "averageReviewTimeMin": 18,
    "monthlyEarnings": 84200,
    "signals": [
        {"id": "sig1", "name": "AI agreement", "value": 92, "target": 85},
        {"id": "sig2", "name": "Peer review match", "value": 96, "target": 90},
        {"id": "sig3", "name": "Time to publish", "value": 88, "target": 80},
        {"id": "sig4", "name": "Candidate fairness", "value": 99, "target": 95},
    ],
    "recentReports": [
        {"id": "r1", "candidate": "Aarav Rao", "skill": "Kafka", "date": "Apr 26", "verdict": "verified", "score": 76},
        {"id": "r2", "candidate": "Priya Nair", "skill": "Payments", "date": "Apr 22", "verdict": "partial", "score": 58},
        {"id": "r3", "candidate": "Omar Haddad", "skill": ".NET", "date": "Apr 18", "verdict": "verified", "score": 83},
    ],
}

SLOTS: list[dict] = [
    {"id": "vs_1", "day": "Mon", "time": "09:00", "duration": 60, "skill": "Kafka", "booked": True, "candidate": "P. Nair"},
    {"id": "vs_2", "day": "Mon", "time": "14:00", "duration": 90, "skill": "System Design", "booked": False},
    {"id": "vs_3", "day": "Tue", "time": "10:00", "duration": 60, "skill": "Any", "booked": False},
    {"id": "vs_4", "day": "Wed", "time": "11:00", "duration": 60, "skill": ".NET Microservices", "booked": True, "candidate": "A. Rao"},
    {"id": "vs_5", "day": "Thu", "time": "15:00", "duration": 60, "skill": "Postgres", "booked": False},
    {"id": "vs_6", "day": "Fri", "time": "09:00", "duration": 60, "skill": "Kafka", "booked": True, "candidate": "O. Haddad"},
    {"id": "vs_7", "day": "Fri", "time": "14:00", "duration": 60, "skill": "Any", "booked": False},
]

EARNINGS: dict = {
    "key": "default",
    "currentMonth": "Apr 2026",
    "currentAmount": 84200,
    "currentSessions": 12,
    "ytdAmount": 332700,
    "ytdSessions": 47,
    "rateStandard": 6700,
    "rateAdvanced": 8000,
    "pending": 0,
    "months": [
        {"id": "em_2026_04", "month": "Apr 2026", "sessions": 12, "hours": 12.5, "amount": 84200, "status": "Paid"},
        {"id": "em_2026_03", "month": "Mar 2026", "sessions": 15, "hours": 15, "amount": 105000, "status": "Paid"},
        {"id": "em_2026_02", "month": "Feb 2026", "sessions": 11, "hours": 11, "amount": 77000, "status": "Paid"},
        {"id": "em_2026_01", "month": "Jan 2026", "sessions": 9, "hours": 9.5, "amount": 66500, "status": "Paid"},
    ],
    "rateCard": [
        {"id": "rc_1", "label": "60-min standard", "value": "₹6,700"},
        {"id": "rc_2", "label": "90-min advanced", "value": "₹10,050"},
        {"id": "rc_3", "label": "30-min follow-up", "value": "₹3,350"},
        {"id": "rc_4", "label": "Urgent (< 24hr)", "value": "₹6,700 + 20%"},
        {"id": "rc_5", "label": "Quality bonus (4.9+)", "value": "+ ₹700 / session"},
    ],
}

PROFILE: dict = {
    "key": "default",
    "name": "Deepa Krishnan",
    "title": "Senior Kafka Practitioner",
    "yearsExperience": 9,
    "rating": 4.9,
    "sessions": 247,
    "bio": (
        "Senior backend engineer with 9 years in distributed systems. Specialise in "
        "Kafka, event-driven architectures, and .NET microservices at scale. Led the "
        "Kafka platform at Razorpay (2019–2023)."
    ),
    "linkedin": "linkedin.com/in/deepakrishnan",
    "language": "English (en-IN)",
    "specializations": [
        "Kafka & Event Streams",
        "Distributed Systems",
        ".NET Microservices",
        "System Design",
    ],
    "pendingReports": 2,
    "quality": [
        {"id": "q1", "metric": "Candidate satisfaction", "value": "96%"},
        {"id": "q2", "metric": "Report accuracy (admin audit)", "value": "98%"},
        {"id": "q3", "metric": "On-time start rate", "value": "100%"},
        {"id": "q4", "metric": "Flagged sessions", "value": "0"},
        {"id": "q5", "metric": "Repeat booking rate", "value": "34%"},
    ],
}

_SINGLETONS = [
    ("verifier_queue", QUEUE),
    ("verifier_brief", BRIEF),
    ("verifier_suggested_gaps", SUGGESTED_GAPS),
    ("verifier_governance", GOVERNANCE),
    ("verifier_earnings", EARNINGS),
    ("verifier_profile", PROFILE),
]


async def seed_verifier() -> int:
    db = get_database()
    inserted = 0

    for coll_name, template in _SINGLETONS:
        coll = db[coll_name]
        if not await coll.find_one({"key": "default"}):
            await coll.insert_one(dict(template))
            inserted += 1

    pending = db["pending_reports"]
    for item in PENDING_REPORTS:
        if not await pending.find_one({"id": item["id"]}):
            await pending.insert_one(dict(item))
            inserted += 1

    reports = db["session_reports"]
    for item in REPORTS:
        if not await reports.find_one({"id": item["id"]}):
            await reports.insert_one(dict(item))
            inserted += 1

    slots = db["verifier_slots"]
    for item in SLOTS:
        if not await slots.find_one({"id": item["id"]}):
            await slots.insert_one(dict(item))
            inserted += 1

    return inserted
