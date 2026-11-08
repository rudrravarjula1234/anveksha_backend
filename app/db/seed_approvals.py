"""Approvals seed data — mirror of anveksha_ui/src/mocks/data/approvals.ts."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import parse_wire, parse_wire_opt

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


async def seed_approvals(db: AsyncSession) -> int:
    from app.models.approvals import (
        ActiveInterviewer,
        InterviewerApproval,
        SpecialistInvite,
    )

    inserted = 0

    for item in APPROVALS:
        if await db.get(InterviewerApproval, item["id"]):
            continue
        db.add(
            InterviewerApproval(
                id=item["id"],
                candidate_id=item["candidateId"],
                candidate_name=item["candidateName"],
                candidate_initials=item["candidateInitials"],
                dossier_id=item["dossierId"],
                requested_skill=item["requestedSkill"],
                origin=item["origin"],
                submitted_at=parse_wire(item["submittedAt"]),
                status=item["status"],
                candidate_score=item.get("candidateScore"),
                candidate_sessions=item.get("candidateSessions"),
                bot_reasoning=item.get("botReasoning"),
                reviewed_by=item.get("reviewedBy"),
                reviewed_at=parse_wire_opt(item.get("reviewedAt")),
            )
        )
        inserted += 1

    for item in INVITES:
        if await db.get(SpecialistInvite, item["id"]):
            continue
        invite = SpecialistInvite(
            id=item["id"],
            email=item["email"],
            first_name=item["firstName"],
            last_name=item["lastName"],
            skill_name=item["skillName"],
            bio=item.get("bio", ""),
            status=item["status"],
            invited_at=parse_wire(item["invitedAt"]),
            invited_by=item["invitedBy"],
            accepted_at=parse_wire_opt(item.get("acceptedAt")),
        )
        invite.external_proofs = [
            {"proof_id": p["id"], "label": p["label"], "url": p["url"]}
            for p in item.get("externalProof", [])
        ]
        db.add(invite)
        inserted += 1

    for item in ACTIVE:
        if await db.get(ActiveInterviewer, item["candidateId"]):
            continue
        active = ActiveInterviewer(
            candidate_id=item["candidateId"],
            candidate_name=item["candidateName"],
            candidate_initials=item["candidateInitials"],
            mode=item["mode"],
            sessions=item.get("sessions", 0),
            rating=item.get("rating"),
            reliability=item.get("reliability"),
            joined_at=parse_wire(item["joinedAt"]),
        )
        active.authorities = [{"skill_name": name} for name in item.get("authorities", [])]
        db.add(active)
        inserted += 1

    if inserted:
        await db.flush()
    return inserted
