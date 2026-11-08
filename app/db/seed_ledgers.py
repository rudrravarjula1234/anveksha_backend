"""Skill-ledger seed data — mirror of anveksha_ui/src/mocks/data/candidate.ts.

One row per persona in the `skill_ledgers` table (Postgres), keyed by
`candidate_id`. Inserted only when missing (idempotent).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import parse_wire, parse_wire_opt

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


def _build_ledger(template: dict):
    from app.models.skill import (
        InterviewerAuthority,
        SkillLedger,
        SkillLedgerRow,
    )

    status = template["interviewerStatus"]
    stats = status.get("stats") or {}
    ledger = SkillLedger(
        candidate_id=template["candidateId"],
        candidate_name=template["candidateName"],
        candidate_title=template["candidateTitle"],
        candidate_location=template["candidateLocation"],
        candidate_initials=template["candidateInitials"],
        dossier_id=template["dossierId"],
        verification_score=template["verificationScore"],
        verified_count=template["verifiedCount"],
        partial_count=template["partialCount"],
        gray_count=template["grayCount"],
        top_percent=template["topPercent"],
        interviewer_mode=status.get("mode", "none"),
        interviewer_origin=status.get("origin"),
        interviewer_approved_by=status.get("approvedBy"),
        interviewer_approved_at=parse_wire_opt(status.get("approvedAt")),
        interviewer_bio=status.get("bio"),
        stats_sessions=stats.get("sessions"),
        stats_rating=stats.get("rating"),
        stats_reliability=stats.get("reliability"),
        stats_peer_score=stats.get("peerScore"),
        stats_appeal_rate=stats.get("appealRate"),
        stats_average_review_minutes=stats.get("averageReviewMinutes"),
        stats_monthly_earnings=stats.get("monthlyEarnings"),
    )
    ledger.skills = [
        SkillLedgerRow(
            skill_id=s["id"],
            name=s["name"],
            state=s["state"],
            depth=s["depth"],
            score=s.get("score"),
            last_verified=s.get("lastVerified"),
            sessions=s.get("sessions", 0),
            report_id=s.get("reportId"),
            authority=s.get("authority"),
            authority_since=parse_wire_opt(s.get("authoritySince")),
        )
        for s in template["skills"]
    ]
    ledger.authorities = [
        InterviewerAuthority(skill_id=a["skillId"], skill_name=a["skillName"], approved_at=parse_wire(a["approvedAt"]))
        for a in status.get("authorities", [])
    ]
    ledger.external_proofs = [
        {"proof_id": p["id"], "label": p["label"], "url": p["url"]}
        for p in status.get("externalProof") or []
    ]
    return ledger


async def seed_skill_ledgers(db: AsyncSession) -> int:
    from app.models.skill import SkillLedger

    inserted = 0
    for template in SEED_LEDGERS:
        existing = await db.get(SkillLedger, template["candidateId"])
        if existing:
            continue
        db.add(_build_ledger(template))
        inserted += 1
    if inserted:
        await db.flush()
    return inserted
