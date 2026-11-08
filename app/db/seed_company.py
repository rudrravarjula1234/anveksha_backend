"""Company-portal seed data — mirror of companyInterviewers.ts,
companyOps.ts, followups.ts and company.ts."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import parse_wire


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

COMPANY: dict = {"id": "co_northstack", "name": "NorthStack Inc.", "primaryDomain": "northstack.co"}

ANON_INTERVIEWERS: list[dict] = [
    {"id": "ai_001", "displayName": "A. Krishnan", "title": "Staff Engineer · Payments", "email": "akrishnan@northstack.co", "specialties": ["Payments", "System Design"], "verified": True, "sessions": 18, "externalSessions": 12, "rating": 4.8, "addedAt": "2026-02-14T09:00:00.000Z"},
    {"id": "ai_002", "displayName": "V. Iyer", "title": "Principal Architect", "email": "viyer@northstack.co", "specialties": [".NET Microservices", "Distributed Systems"], "verified": True, "sessions": 24, "externalSessions": 20, "rating": 4.9, "addedAt": "2026-01-20T09:00:00.000Z"},
    {"id": "ai_003", "displayName": "M. Rao", "title": "Senior Backend Engineer", "email": "mrao@northstack.co", "specialties": ["Kafka", "Postgres"], "verified": False, "sessions": 0, "externalSessions": 0, "addedAt": "2026-05-28T09:00:00.000Z"},
]

# Ledger transactions in order; balanceAfter computed at seed time.
_CREDIT_TX: list[dict] = [
    {"id": "tx_001", "at": "2026-03-04T10:00:00.000Z", "kind": "earned", "amount": 200, "reason": "External session · ai_001 · payments verification", "interviewerId": "ai_001"},
    {"id": "tx_002", "at": "2026-03-18T09:30:00.000Z", "kind": "earned", "amount": 200, "reason": "External session · ai_002 · .NET microservices verification", "interviewerId": "ai_002"},
    {"id": "tx_003", "at": "2026-04-02T14:00:00.000Z", "kind": "spent", "amount": 50, "reason": "Unlock candidate · Aarav Rao"},
    {"id": "tx_004", "at": "2026-04-12T11:15:00.000Z", "kind": "earned", "amount": 200, "reason": "External session · ai_001 · system design verification", "interviewerId": "ai_001"},
    {"id": "tx_005", "at": "2026-04-26T16:00:00.000Z", "kind": "spent", "amount": 80, "reason": "Gray follow-up request · Kafka Streams"},
    {"id": "tx_006", "at": "2026-05-08T09:45:00.000Z", "kind": "earned", "amount": 200, "reason": "External session · ai_002 · distributed systems", "interviewerId": "ai_002"},
    {"id": "tx_007", "at": "2026-05-22T13:30:00.000Z", "kind": "spent", "amount": 100, "reason": "Unlock candidate · Priya Nair"},
]

CREDIT_RATE: dict = {"key": "default", "rupeesPerCredit": 10, "updatedAt": "2026-01-01T00:00:00.000Z", "updatedBy": "usr_adm_001"}

TEAM: list[dict] = [
    {"id": "tm_001", "name": "Rahul Mishra", "email": "rahul@northstack.co", "role": "Hiring Manager", "pipelines": 8, "lastActive": "1h ago", "status": "active"},
    {"id": "tm_002", "name": "Ananya Bose", "email": "ananya@northstack.co", "role": "Recruiter", "pipelines": 3, "lastActive": "3h ago", "status": "active"},
    {"id": "tm_003", "name": "Karan Mehta", "email": "karan@northstack.co", "role": "Recruiter", "pipelines": 2, "lastActive": "2d ago", "status": "active"},
    {"id": "tm_004", "name": "Sia Kapoor", "email": "sia@northstack.co", "role": "Viewer", "pipelines": 0, "lastActive": "1w ago", "status": "inactive"},
]

BILLING: dict = {
    "key": "default",
    "summary": {
        "plan": "Enterprise", "seats": 25, "seatsUsed": 4, "monthlyAmount": 120000,
        "nextBilling": "May 1, 2026",
        "includes": ["Unlimited AI chats", "Priority follow-ups", "Single sign-on", "Audit log"],
        "aiChatsUsed": 487, "aiChatsIncluded": 1000,
    },
    "invoices": [
        {"id": "inv_2026_04", "month": "Apr 2026", "amount": 120000, "status": "Paid", "pdfUrl": "/invoices/2026-04.pdf"},
        {"id": "inv_2026_03", "month": "Mar 2026", "amount": 120000, "status": "Paid", "pdfUrl": "/invoices/2026-03.pdf"},
        {"id": "inv_2026_02", "month": "Feb 2026", "amount": 95000, "status": "Paid", "pdfUrl": "/invoices/2026-02.pdf"},
        {"id": "inv_2026_01", "month": "Jan 2026", "amount": 95000, "status": "Paid", "pdfUrl": "/invoices/2026-01.pdf"},
    ],
}

GRAY_FOLLOWUPS: list[dict] = [
    {"id": "fu_001", "candidate": "Aarav Rao", "candidateId": "cand_001", "grayArea": "Kafka Streams", "asked": 4, "requested": "Apr 25", "status": "requested", "companies": "NorthStack · Razorpay · Meesho"},
    {"id": "fu_002", "candidate": "Aarav Rao", "candidateId": "cand_001", "grayArea": "Payments Domain", "asked": 3, "requested": "Apr 22", "status": "accepted", "scheduled": "May 3 · 14:00"},
    {"id": "fu_003", "candidate": "Omar Haddad", "candidateId": "cand_003", "grayArea": "Redis Streams", "asked": 2, "requested": "Apr 20", "status": "pending"},
    {"id": "fu_004", "candidate": "Li Wei", "candidateId": "cand_004", "grayArea": "Payments Domain", "asked": 5, "requested": "Apr 15", "status": "completed", "score": 81},
]

SEARCH_CANDIDATES: list[dict] = [
    {"id": "cand_001", "name": "Aarav Rao", "initials": "A", "title": "Backend Engineer", "years": 6, "location": "Bengaluru", "verificationScore": 76, "matchPercent": 94, "verifiedSkills": ["Kafka", "System Design", ".NET Microservices"], "graySkills": ["Kafka Streams"], "lastActivity": "2d ago"},
    {"id": "cand_002", "name": "Priya Nair", "initials": "P", "title": "Staff Engineer", "years": 9, "location": "Pune", "verificationScore": 88, "matchPercent": 89, "verifiedSkills": ["Payments", "System Design"], "graySkills": ["Event Sourcing"], "lastActivity": "4d ago"},
    {"id": "cand_003", "name": "Omar Haddad", "initials": "O", "title": "Senior Engineer", "years": 5, "location": "Dubai", "verificationScore": 71, "matchPercent": 82, "verifiedSkills": [".NET", "Microservices"], "graySkills": ["Kafka", "Redis Streams"], "lastActivity": "1w ago"},
    {"id": "cand_004", "name": "Li Wei", "initials": "L", "title": "Principal Engineer", "years": 11, "location": "Singapore", "verificationScore": 92, "matchPercent": 78, "verifiedSkills": ["System Design", "Postgres"], "graySkills": ["Payments domain"], "lastActivity": "3d ago"},
]

SEARCH_FACETS: dict = {
    "skills": [{"name": "Kafka", "count": 12}, {"name": "System Design", "count": 9}, {"name": "Payments", "count": 4}],
    "locations": [{"name": "India", "count": 7}, {"name": "APAC", "count": 5}, {"name": "EU", "count": 3}],
}

PIPELINE_CARDS: list[dict] = [
    {"candidateId": "cand_001", "name": "Aarav Rao", "initials": "A", "matchPercent": 94, "lastActivity": "2d ago", "stage": "investigating", "note": "Dossier requested"},
    {"candidateId": "cand_003", "name": "Omar Haddad", "initials": "O", "matchPercent": 82, "lastActivity": "1w ago", "stage": "investigating"},
    {"candidateId": "cand_004", "name": "Li Wei", "initials": "L", "matchPercent": 78, "lastActivity": "3d ago", "stage": "followup", "note": "Payments follow-up pending"},
    {"candidateId": "cand_002", "name": "Priya Nair", "initials": "P", "matchPercent": 89, "lastActivity": "4d ago", "stage": "shortlist"},
]

FOLLOWUP_SKILLS: list[dict] = [
    {"id": "fs1", "name": "Payments idempotency", "requested": 4},
    {"id": "fs2", "name": "Kafka Streams", "requested": 3},
    {"id": "fs3", "name": "Cross-region replication", "requested": 2},
    {"id": "fs4", "name": "gRPC", "requested": 1},
]


async def seed_company(db: AsyncSession) -> int:
    from app.models.company import (
        AnonymousInterviewer,
        Billing,
        Company,
        CreditRate,
        CreditTransaction,
        FollowupSkillOption,
        GrayFollowup,
        PipelineCard,
        SearchCandidate,
        SearchFacets,
        TeamMember,
    )

    inserted = 0

    if not await db.get(Company, COMPANY["id"]):
        db.add(
            Company(
                id=COMPANY["id"], name=COMPANY["name"], primary_domain=COMPANY["primaryDomain"],
                credit_balance=0,  # set for real below, once the ledger is seeded
            )
        )
        inserted += 1
        await db.flush()

    for item in ANON_INTERVIEWERS:
        if await db.get(AnonymousInterviewer, item["id"]):
            continue
        db.add(
            AnonymousInterviewer(
                id=item["id"], display_name=item["displayName"], title=item["title"], email=item["email"],
                specialties=item["specialties"], verified=item["verified"], sessions=item["sessions"],
                external_sessions=item["externalSessions"], rating=item.get("rating"), added_at=parse_wire(item["addedAt"]),
            )
        )
        inserted += 1

    balance = 0
    for tx in _CREDIT_TX:
        balance += tx["amount"] if tx["kind"] == "earned" else -tx["amount"]
        if await db.get(CreditTransaction, tx["id"]):
            continue
        db.add(
            CreditTransaction(
                id=tx["id"], at=_parse_iso(tx["at"]), kind=tx["kind"], amount=tx["amount"],
                reason=tx["reason"], balance_after=balance, interviewer_id=tx.get("interviewerId"),
            )
        )
        inserted += 1
    company = await db.get(Company, COMPANY["id"])
    if company is not None:
        company.credit_balance = balance  # maintained column — set once from the seeded ledger

    if not await db.get(CreditRate, "default"):
        db.add(
            CreditRate(
                id="default", rupees_per_credit=CREDIT_RATE["rupeesPerCredit"],
                rate_updated_at=parse_wire(CREDIT_RATE["updatedAt"]), updated_by=CREDIT_RATE["updatedBy"],
            )
        )
        inserted += 1

    for item in TEAM:
        if await db.get(TeamMember, item["id"]):
            continue
        db.add(
            TeamMember(
                id=item["id"], name=item["name"], email=item["email"], role=item["role"],
                pipelines=item["pipelines"], last_active=item["lastActive"], status=item["status"],
            )
        )
        inserted += 1

    if not await db.get(Billing, "default"):
        summary = BILLING["summary"]
        row = Billing(
            id="default", plan=summary["plan"], seats=summary["seats"], seats_used=summary["seatsUsed"],
            monthly_amount=summary["monthlyAmount"], next_billing=summary["nextBilling"],
            includes=summary["includes"], ai_chats_used=summary["aiChatsUsed"],
            ai_chats_included=summary["aiChatsIncluded"],
        )
        row.invoices = [
            {"id": i["id"], "month": i["month"], "amount": i["amount"], "status": i["status"],
             "pdf_url": i["pdfUrl"]}
            for i in BILLING["invoices"]
        ]
        db.add(row)
        inserted += 1

    for item in SEARCH_CANDIDATES:
        if await db.get(SearchCandidate, item["id"]):
            continue
        db.add(
            SearchCandidate(
                id=item["id"], name=item["name"], initials=item["initials"], title=item["title"],
                years=item["years"], location=item["location"], verification_score=item["verificationScore"],
                match_percent=item["matchPercent"], verified_skills=item["verifiedSkills"],
                gray_skills=item["graySkills"], last_activity=item["lastActivity"],
            )
        )
        inserted += 1
    await db.flush()  # search_candidates must exist before FK-dependent rows below

    for item in GRAY_FOLLOWUPS:
        if await db.get(GrayFollowup, item["id"]):
            continue
        db.add(
            GrayFollowup(
                id=item["id"], candidate=item["candidate"], candidate_id=item["candidateId"],
                gray_area=item["grayArea"], asked=item["asked"], requested=item["requested"],
                status=item["status"], companies=item.get("companies"), scheduled=item.get("scheduled"),
                score=item.get("score"),
            )
        )
        inserted += 1

    if not await db.get(SearchFacets, "default"):
        db.add(SearchFacets(id="default", skills=SEARCH_FACETS["skills"], locations=SEARCH_FACETS["locations"]))
        inserted += 1

    for item in PIPELINE_CARDS:
        if await db.get(PipelineCard, item["candidateId"]):
            continue
        db.add(
            PipelineCard(
                candidate_id=item["candidateId"], name=item["name"], initials=item["initials"],
                match_percent=item["matchPercent"], last_activity=item["lastActivity"], stage=item["stage"],
                note=item.get("note"),
            )
        )
        inserted += 1

    for item in FOLLOWUP_SKILLS:
        if await db.get(FollowupSkillOption, item["id"]):
            continue
        db.add(FollowupSkillOption(id=item["id"], name=item["name"], requested=item["requested"]))
        inserted += 1

    if inserted:
        await db.flush()
    return inserted
