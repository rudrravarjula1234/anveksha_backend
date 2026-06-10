"""Company-portal seed data — mirror of companyInterviewers.ts,
companyOps.ts, followups.ts and company.ts."""

from app.db.mongo import get_database

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


async def seed_company() -> int:
    db = get_database()
    inserted = 0

    if not await db["companies"].find_one({"id": COMPANY["id"]}):
        await db["companies"].insert_one(dict(COMPANY))
        inserted += 1

    for item in ANON_INTERVIEWERS:
        if not await db["anonymous_interviewers"].find_one({"id": item["id"]}):
            await db["anonymous_interviewers"].insert_one(dict(item))
            inserted += 1

    tx_coll = db["credit_transactions"]
    balance = 0
    for tx in _CREDIT_TX:
        balance += tx["amount"] if tx["kind"] == "earned" else -tx["amount"]
        if not await tx_coll.find_one({"id": tx["id"]}):
            await tx_coll.insert_one({**tx, "balanceAfter": balance})
            inserted += 1

    if not await db["credit_rate"].find_one({"key": "default"}):
        await db["credit_rate"].insert_one(dict(CREDIT_RATE))
        inserted += 1

    for item in TEAM:
        if not await db["team_members"].find_one({"id": item["id"]}):
            await db["team_members"].insert_one(dict(item))
            inserted += 1

    if not await db["billing"].find_one({"key": "default"}):
        await db["billing"].insert_one(dict(BILLING))
        inserted += 1

    for item in GRAY_FOLLOWUPS:
        if not await db["gray_followups"].find_one({"id": item["id"]}):
            await db["gray_followups"].insert_one(dict(item))
            inserted += 1

    for item in SEARCH_CANDIDATES:
        if not await db["search_candidates"].find_one({"id": item["id"]}):
            await db["search_candidates"].insert_one(dict(item))
            inserted += 1

    if not await db["search_facets"].find_one({"key": "default"}):
        await db["search_facets"].insert_one({"key": "default", **SEARCH_FACETS})
        inserted += 1

    for item in PIPELINE_CARDS:
        if not await db["pipeline_cards"].find_one({"candidateId": item["candidateId"]}):
            await db["pipeline_cards"].insert_one(dict(item))
            inserted += 1

    for item in FOLLOWUP_SKILLS:
        if not await db["followup_skills"].find_one({"id": item["id"]}):
            await db["followup_skills"].insert_one(dict(item))
            inserted += 1

    return inserted
