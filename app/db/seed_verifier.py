"""Verifier seed data — mirror of verifier.ts + verifierOps.ts.

Singletons (brief, governance, earnings, profile) are stored as one row
each with `id = "default"` — multi-verifier support later swaps the id
for the verifier's user id. `queue`'s `live`/`upcoming`/`completed`
sessions are real `verifier_sessions` rows; its stats tile has no table
of its own — see app/models/verifier.py's module docstring.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timefmt import parse_wire

QUEUE: dict = {
    "key": "default",
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

async def seed_verifier(db: AsyncSession) -> int:
    from app.models.verifier import (
        PendingReport,
        SessionReport,
        SuggestedGap,
        VerifierConsoleState,
        VerifierSession,
        VerifierSlot,
    )

    inserted = 0

    for lane in ("live", "upcoming", "completed"):
        for item in QUEUE[lane]:
            if await db.get(VerifierSession, item["id"]):
                continue
            db.add(
                VerifierSession(
                    id=item["id"], lane=lane, raw_id=item["rawId"], time=item["time"], date=item["date"],
                    candidate=item["candidate"], candidate_initials=item["candidateInitials"],
                    skill=item["skill"], duration=item["duration"], status=item["status"],
                    tags=item.get("tags", []), depth=item.get("depth", ""),
                )
            )
            inserted += 1

    if not await db.get(VerifierConsoleState, "default"):
        row = VerifierConsoleState(
            id="default", session_id=BRIEF["sessionId"], candidate=BRIEF["candidate"],
            skill=BRIEF["skill"], summary=BRIEF["summary"],
            prioritized_probes=BRIEF["prioritizedProbes"], gray_requested=BRIEF["grayRequested"],
            reliability=GOVERNANCE["reliability"], score_variance=GOVERNANCE["scoreVariance"],
            candidate_rating=GOVERNANCE["candidateRating"], appeal_rate=GOVERNANCE["appealRate"],
            average_review_time_min=GOVERNANCE["averageReviewTimeMin"],
            current_month=EARNINGS["currentMonth"], current_amount=EARNINGS["currentAmount"],
            current_sessions=EARNINGS["currentSessions"], ytd_amount=EARNINGS["ytdAmount"],
            ytd_sessions=EARNINGS["ytdSessions"], rate_standard=EARNINGS["rateStandard"],
            rate_advanced=EARNINGS["rateAdvanced"], pending=EARNINGS["pending"],
            name=PROFILE["name"], title=PROFILE["title"],
            years_experience=PROFILE["yearsExperience"], rating=PROFILE["rating"],
            sessions=PROFILE["sessions"], bio=PROFILE["bio"], linkedin=PROFILE["linkedin"],
            language=PROFILE["language"], specializations=PROFILE["specializations"],
            pending_reports=PROFILE["pendingReports"],
        )
        row.signals = [
            {"signal_id": s["id"], "name": s["name"], "value": s["value"], "target": s["target"]}
            for s in GOVERNANCE["signals"]
        ]
        # r1 is the same report as session_reports rpt_001 (Aarav/Kafka/76)
        # — the only recentReports entry with a known session_reports match.
        _session_report_links = {"r1": "rpt_001"}
        row.recent_reports = [
            {
                "report_id": r["id"], "candidate": r["candidate"], "skill": r["skill"], "date": r["date"],
                "verdict": r["verdict"], "score": r["score"],
                "session_report_id": _session_report_links.get(r["id"]),
            }
            for r in GOVERNANCE["recentReports"]
        ]
        row.months = [
            {
                "month_id": m["id"], "month": m["month"], "sessions": m["sessions"], "hours": m["hours"],
                "amount": m["amount"], "status": m["status"],
            }
            for m in EARNINGS["months"]
        ]
        row.rate_card = [
            {"row_id": r["id"], "label": r["label"], "value": r["value"]} for r in EARNINGS["rateCard"]
        ]
        row.quality = [
            {"metric_id": q["id"], "metric": q["metric"], "value": q["value"]} for q in PROFILE["quality"]
        ]
        db.add(row)
        inserted += 1

    for item in SUGGESTED_GAPS["gaps"]:
        if await db.get(SuggestedGap, item["id"]):
            continue
        db.add(
            SuggestedGap(
                id=item["id"], text=item["text"], sub=item.get("sub", ""),
                accepted=item.get("accepted", False), note=item.get("note"),
            )
        )
        inserted += 1

    for item in PENDING_REPORTS:
        if await db.get(PendingReport, item["id"]):
            continue
        db.add(
            PendingReport(
                id=item["id"], session_id=item["sessionId"], candidate=item["candidate"],
                initials=item["initials"], skill=item["skill"], date=item["date"], ai_score=item["aiScore"],
            )
        )
        inserted += 1

    for item in REPORTS:
        if await db.get(SessionReport, item["id"]):
            continue
        # rpt_001 is the same report as skill_report_details SVR-KAF-88421
        # (Aarav/Kafka/76) — the only REPORTS entry with a known match.
        _published_links = {"rpt_001": "SVR-KAF-88421"}
        row = SessionReport(
            id=item["id"], session_id=item["sessionId"], candidate_name=item["candidateName"],
            skill=item["skill"], verdict=item["verdict"], overall_score=item["overallScore"],
            gray_areas=item.get("grayAreas", []), strengths=item.get("strengths", []),
            status=item["status"], report_created_at=parse_wire(item["createdAt"]),
            published_report_id=_published_links.get(item["id"]),
        )
        row.sections = [
            {
                "section_id": s["id"], "title": s["title"], "ai_score": s["aiScore"],
                "verifier_score": s.get("verifierScore"), "notes": s.get("notes", ""),
                "evidence": s.get("evidence", []),
            }
            for s in item["sections"]
        ]
        db.add(row)
        inserted += 1

    for item in SLOTS:
        if await db.get(VerifierSlot, item["id"]):
            continue
        db.add(
            VerifierSlot(
                id=item["id"], day=item["day"], time=item["time"], duration=item["duration"],
                skill=item["skill"], booked=item.get("booked", False), candidate=item.get("candidate"),
            )
        )
        inserted += 1

    if inserted:
        await db.flush()
    return inserted
