"""Approvals seed data — mirror of anveksha_ui/src/mocks/data/approvals.ts."""

from app.db.mongo import get_database

APPROVALS: list[dict] = [
    {
        "id": "apr_001",
        "candidateId": "usr_cand_001",
        "candidateName": "Aarav Rao",
        "candidateInitials": "A",
        "dossierId": "ANV-2481",
        "requestedSkill": ".NET Microservices",
        "origin": "bot-discovered",
        "submittedAt": "2026-05-30T08:14:00.000Z",
        "status": "pending",
        "candidateScore": 87,
        "candidateSessions": 2,
        "botReasoning": "Scored 87/100 in .NET Microservices · 2 sessions in last 90 days · zero integrity flags · ranks top 6% in cohort.",
    },
    {
        "id": "apr_002",
        "candidateId": "usr_cand_018",
        "candidateName": "Priya Nair",
        "candidateInitials": "P",
        "dossierId": "ANV-3902",
        "requestedSkill": "Payments System Design",
        "origin": "self-requested",
        "submittedAt": "2026-05-28T16:22:00.000Z",
        "status": "pending",
        "candidateScore": 88,
        "candidateSessions": 1,
    },
    {
        "id": "apr_003",
        "candidateId": "usr_cand_044",
        "candidateName": "Rohit Verma",
        "candidateInitials": "R",
        "dossierId": "ANV-4419",
        "requestedSkill": "Postgres & Indexing",
        "origin": "bot-discovered",
        "submittedAt": "2026-05-25T11:00:00.000Z",
        "status": "pending",
        "candidateScore": 74,
        "candidateSessions": 1,
        "botReasoning": "Scored 74/100 in Postgres & Indexing · only 1 session · borderline; recommend manual review.",
    },
    {
        "id": "apr_900",
        "candidateId": "usr_ver_001",
        "candidateName": "Maya Iyer",
        "candidateInitials": "M",
        "dossierId": "ANV-7104",
        "requestedSkill": ".NET Microservices",
        "origin": "bot-discovered",
        "submittedAt": "2025-11-10T09:00:00.000Z",
        "status": "approved",
        "candidateScore": 91,
        "candidateSessions": 2,
        "reviewedBy": "usr_adm_001",
        "reviewedAt": "2025-11-12T10:30:00.000Z",
    },
]

INVITES: list[dict] = [
    {
        "id": "inv_001",
        "email": "suresh.mehra@anveksha.dev",
        "firstName": "Suresh",
        "lastName": "Mehra",
        "skillName": "System Design",
        "bio": "Principal architect with 18 years across payments and infra. Designed the order-processing pipeline that handles 14M transactions/day at a top-three Indian fintech.",
        "externalProof": [
            {"id": "ep1", "label": "LinkedIn", "url": "https://www.linkedin.com/in/suresh-mehra"},
            {"id": "ep2", "label": "QCon Bengaluru 2024 — Distributed Sagas", "url": "https://qconbengaluru.com/2024/sagas"},
        ],
        "status": "accepted",
        "invitedAt": "2025-08-25T09:00:00.000Z",
        "invitedBy": "usr_adm_001",
        "acceptedAt": "2025-09-01T09:00:00.000Z",
    },
    {
        "id": "inv_002",
        "email": "arundhati.swamy@example.com",
        "firstName": "Arundhati",
        "lastName": "Swamy",
        "skillName": "Distributed Systems",
        "bio": "CTO at PayStash. 22 years in core banking & high-throughput ledgers.",
        "externalProof": [
            {"id": "ep1", "label": "GitHub", "url": "https://github.com/aswamy"},
            {"id": "ep2", "label": "Paper: Saga choreography at scale", "url": "https://example.com/saga"},
        ],
        "status": "sent",
        "invitedAt": "2026-05-22T10:00:00.000Z",
        "invitedBy": "usr_adm_001",
    },
]

ACTIVE: list[dict] = [
    {
        "candidateId": "usr_ver_001",
        "candidateName": "Maya Iyer",
        "candidateInitials": "M",
        "mode": "freelance",
        "authorities": [".NET Microservices", "System Design"],
        "sessions": 247,
        "rating": 4.9,
        "reliability": 98,
        "joinedAt": "2025-11-12T10:30:00.000Z",
    },
    {
        "candidateId": "usr_spec_001",
        "candidateName": "Dr. Suresh Mehra",
        "candidateInitials": "S",
        "mode": "specialist",
        "authorities": ["System Design", "Distributed Systems"],
        "sessions": 64,
        "rating": 4.95,
        "reliability": 99,
        "joinedAt": "2025-09-01T09:00:00.000Z",
    },
]


async def seed_approvals() -> int:
    db = get_database()
    inserted = 0

    approvals = db["interviewer_approvals"]
    for item in APPROVALS:
        if not await approvals.find_one({"id": item["id"]}):
            await approvals.insert_one(dict(item))
            inserted += 1

    invites = db["specialist_invites"]
    for item in INVITES:
        if not await invites.find_one({"id": item["id"]}):
            await invites.insert_one(dict(item))
            inserted += 1

    active = db["active_interviewers"]
    for item in ACTIVE:
        if not await active.find_one({"candidateId": item["candidateId"]}):
            await active.insert_one(dict(item))
            inserted += 1

    return inserted
