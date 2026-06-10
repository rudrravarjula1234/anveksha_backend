"""Skill-ledger seed data — mirror of anveksha_ui/src/mocks/data/candidate.ts.

One document per persona in the `skill_ledgers` collection, keyed by
`candidateId`. Inserted only when missing (idempotent).
"""

from app.db.mongo import get_database

AARAV_LEDGER: dict = {
    "candidateId": "usr_cand_001",
    "candidateName": "Aarav Rao",
    "candidateTitle": "Backend Engineer · 6 yrs",
    "candidateLocation": "Bengaluru",
    "candidateInitials": "A",
    "dossierId": "ANV-2481",
    "verificationScore": 78,
    "verifiedCount": 4,
    "partialCount": 1,
    "grayCount": 7,
    "topPercent": 12,
    "interviewerStatus": {"mode": "none", "authorities": []},
    "skills": [
        {
            "id": "skl_001",
            "name": ".NET Microservices",
            "state": "verified",
            "depth": "Advanced",
            "score": 87,
            "lastVerified": "Mar 14",
            "sessions": 2,
            "reportId": "SVR-NET-65433",
        },
        {
            "id": "skl_002",
            "name": "System Design",
            "state": "verified",
            "depth": "Advanced",
            "score": 82,
            "lastVerified": "Feb 02",
            "sessions": 1,
            "reportId": "SVR-SYS-72110",
        },
        {
            "id": "skl_003",
            "name": "Distributed Systems",
            "state": "partial",
            "depth": "Intermediate",
            "score": 64,
            "lastVerified": "Feb 02",
            "sessions": 1,
            "reportId": "SVR-DS-44918",
        },
        {
            "id": "skl_004",
            "name": "Postgres & Indexing",
            "state": "verified",
            "depth": "Intermediate",
            "score": 78,
            "lastVerified": "Jan 18",
            "sessions": 1,
            "reportId": "SVR-PG-51200",
        },
        {
            "id": "skl_005",
            "name": "Kafka & Event Streams",
            "state": "gray",
            "depth": "Not tested",
            "score": None,
            "lastVerified": None,
            "sessions": 0,
            "reportId": None,
        },
        {
            "id": "skl_006",
            "name": "React / Next.js",
            "state": "claimed",
            "depth": "Claimed only",
            "score": None,
            "lastVerified": None,
            "sessions": 0,
            "reportId": None,
        },
    ],
}

MAYA_LEDGER: dict = {
    "candidateId": "usr_ver_001",
    "candidateName": "Maya Iyer",
    "candidateTitle": "Staff Engineer · 9 yrs",
    "candidateLocation": "Hyderabad",
    "candidateInitials": "M",
    "dossierId": "ANV-7104",
    "verificationScore": 88,
    "verifiedCount": 3,
    "partialCount": 0,
    "grayCount": 2,
    "topPercent": 8,
    "interviewerStatus": {
        "mode": "freelance",
        "origin": "bot-discovered",
        "approvedBy": "usr_adm_001",
        "approvedAt": "2025-11-12T10:30:00.000Z",
        "authorities": [
            {
                "skillId": "skl_m1",
                "skillName": ".NET Microservices",
                "approvedAt": "2025-11-12T10:30:00.000Z",
            },
            {
                "skillId": "skl_m2",
                "skillName": "System Design",
                "approvedAt": "2025-12-04T14:00:00.000Z",
            },
        ],
        "stats": {
            "sessions": 247,
            "rating": 4.9,
            "reliability": 98,
            "peerScore": 92,
            "appealRate": 1.2,
            "averageReviewMinutes": 18,
            "monthlyEarnings": 84200,
        },
    },
    "skills": [
        {
            "id": "skl_m1",
            "name": ".NET Microservices",
            "state": "verified",
            "depth": "Advanced",
            "score": 91,
            "lastVerified": "Sep 14",
            "sessions": 2,
            "reportId": "SVR-NET-71001",
            "authority": True,
            "authoritySince": "2025-11-12T10:30:00.000Z",
        },
        {
            "id": "skl_m2",
            "name": "System Design",
            "state": "verified",
            "depth": "Advanced",
            "score": 88,
            "lastVerified": "Aug 02",
            "sessions": 1,
            "reportId": "SVR-SYS-71002",
            "authority": True,
            "authoritySince": "2025-12-04T14:00:00.000Z",
        },
        {
            "id": "skl_m3",
            "name": "Postgres & Indexing",
            "state": "verified",
            "depth": "Intermediate",
            "score": 82,
            "lastVerified": "Jul 18",
            "sessions": 1,
            "reportId": "SVR-PG-71003",
        },
        {
            "id": "skl_m4",
            "name": "React / Next.js",
            "state": "gray",
            "depth": "Not tested",
            "score": None,
            "lastVerified": None,
            "sessions": 0,
            "reportId": None,
        },
        {
            "id": "skl_m5",
            "name": "Kubernetes",
            "state": "gray",
            "depth": "Not tested",
            "score": None,
            "lastVerified": None,
            "sessions": 0,
            "reportId": None,
        },
    ],
}

SURESH_LEDGER: dict = {
    "candidateId": "usr_spec_001",
    "candidateName": "Dr. Suresh Mehra",
    "candidateTitle": "Principal Architect · 18 yrs · Invited specialist",
    "candidateLocation": "Bengaluru",
    "candidateInitials": "S",
    "dossierId": "ANV-8801",
    "verificationScore": 0,
    "verifiedCount": 0,
    "partialCount": 0,
    "grayCount": 0,
    "topPercent": 0,
    "interviewerStatus": {
        "mode": "specialist",
        "origin": "admin-invited",
        "approvedBy": "usr_adm_001",
        "approvedAt": "2025-09-01T09:00:00.000Z",
        "authorities": [
            {
                "skillId": "auth_sys",
                "skillName": "System Design",
                "approvedAt": "2025-09-01T09:00:00.000Z",
            },
            {
                "skillId": "auth_dis",
                "skillName": "Distributed Systems",
                "approvedAt": "2025-09-01T09:00:00.000Z",
            },
        ],
        "bio": (
            "Principal architect with 18 years across payments and infra. "
            "Designed the order-processing pipeline that handles 14M "
            "transactions/day at a top-three Indian fintech. Frequent QCon "
            "speaker; author of two O'Reilly chapters on distributed transactions."
        ),
        "externalProof": [
            {"id": "ep1", "label": "LinkedIn", "url": "https://www.linkedin.com/in/suresh-mehra"},
            {
                "id": "ep2",
                "label": "QCon Bengaluru 2024 — Distributed Sagas",
                "url": "https://qconbengaluru.com/2024/sagas",
            },
            {
                "id": "ep3",
                "label": "O'Reilly chapter — Idempotent Payments",
                "url": "https://www.oreilly.com/library/view/idempotent-payments",
            },
        ],
        "stats": {"sessions": 64, "rating": 4.95, "reliability": 99},
    },
    "skills": [],
}

SEED_LEDGERS = [AARAV_LEDGER, MAYA_LEDGER, SURESH_LEDGER]


async def seed_skill_ledgers() -> int:
    db = get_database()
    coll = db["skill_ledgers"]
    inserted = 0
    for template in SEED_LEDGERS:
        existing = await coll.find_one({"candidateId": template["candidateId"]})
        if existing:
            continue
        await coll.insert_one(dict(template))
        inserted += 1
    return inserted
