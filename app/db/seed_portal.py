"""Privacy, dossier, booking + live-session seeds.

Mirrors privacySettings (admin.ts), candidateDossier, bookingCatalog and
liveSessionSnapshot (candidate.ts). Privacy settings are stored per user
so each persona owns their controls.
"""

from app.db.mongo import get_database
from app.db.seed_ledgers import AARAV_LEDGER

_PRIVACY_DEFAULTS: dict = {
    "shareProfile": True,
    "shareDossiers": True,
    "shareTranscripts": False,
    "allowGrayFollowups": True,
    "hideFromCompanies": [],
    "discoverability": "verified-only",
    "shareScore": True,
    "shareGap": False,
    "shareGray": False,
    "shareTranscript": False,
    "allowFollowup": True,
    "anonymousMode": False,
    "shareVerifierPanel": True,
}

_AARAV_SHARED = [
    {
        "id": "sr_001",
        "reportId": "SVR-KAF-88421",
        "sharedWith": "NorthStack Inc.",
        "sharedAt": "2026-04-26T12:00:00.000Z",
        "expiresAt": "2026-05-26T12:00:00.000Z",
        "status": "active",
    },
    {
        "id": "sr_002",
        "reportId": "SVR-NET-65433",
        "sharedWith": "TechCorp India",
        "sharedAt": "2026-04-10T09:00:00.000Z",
        "expiresAt": "2026-05-10T09:00:00.000Z",
        "status": "expired",
    },
]

PRIVACY_SEEDS: list[dict] = [
    {"userId": "usr_cand_001", **_PRIVACY_DEFAULTS, "sharedReports": _AARAV_SHARED},
    {"userId": "usr_ver_001", **_PRIVACY_DEFAULTS, "sharedReports": []},
    {"userId": "usr_spec_001", **_PRIVACY_DEFAULTS, "sharedReports": []},
]

DOSSIER: dict = {
    "id": "SVR-KAF-88421",
    "candidateId": "usr_cand_001",
    "candidateName": "Aarav Rao",
    "candidateInitials": "A",
    "candidateTitle": "Backend Engineer",
    "candidateLocation": "Bengaluru",
    "years": 6,
    "verificationScore": 76,
    "ledger": {k: v for k, v in AARAV_LEDGER.items()},
    "sessions": [
        {"id": "ses_001", "date": "Apr 26, 2026", "skill": "Kafka & Event Streams", "verifier": "Deepa Krishnan", "score": 76, "duration": 60, "verdict": "verified"},
        {"id": "ses_002", "date": "Mar 14, 2026", "skill": ".NET Microservices", "verifier": "S. Mehra", "score": 87, "duration": 60, "verdict": "verified"},
        {"id": "ses_003", "date": "Feb 02, 2026", "skill": "System Design", "verifier": "R. Kapoor", "score": 82, "duration": 60, "verdict": "verified"},
        {"id": "ses_004", "date": "Jan 18, 2026", "skill": "Postgres & Indexing", "verifier": "D. Krishnan", "score": 78, "duration": 45, "verdict": "verified"},
    ],
    "grayAreas": ["Cross-region replication", "Kafka Streams / KSQL", "Tiered storage ops", "Stream-table duality"],
    "strengths": ["Partitioning strategy", "Consumer group semantics", "Transactional producers", "Schema registry hygiene"],
    "isShared": False,
}

BOOKING_CATALOG: dict = {
    "catalogId": "KAF-204",
    "skillName": "Kafka & Event Streams",
    "description": "Live evaluation of real-world event-streaming experience. Discussion-based with a whiteboarding segment. No prepared questions — the verifier probes depth based on your claims.",
    "depth": "Intermediate → Advanced",
    "duration": 60,
    "style": "Discussion + whiteboard",
    "format": "Live session, 1:1 with verifier",
    "evidence": "Transcript, whiteboard, AI insights",
    "probes": "Partitioning & ordering guarantees · Consumer group semantics · Exactly-once delivery · Replay & compaction · Your real production incidents.",
    "weekRange": "IST · Apr 22 – Apr 28",
    "days": [
        {"id": "d1", "day": "Tue", "date": "22", "status": "avail", "slotCount": 5},
        {"id": "d2", "day": "Wed", "date": "23", "status": "avail", "slotCount": 5},
        {"id": "d3", "day": "Thu", "date": "24", "status": "full", "slotCount": 0},
        {"id": "d4", "day": "Fri", "date": "25", "status": "avail", "slotCount": 5},
        {"id": "d5", "day": "Sat", "date": "26", "status": "avail", "slotCount": 5},
        {"id": "d6", "day": "Sun", "date": "27", "status": "avail", "slotCount": 5},
        {"id": "d7", "day": "Mon", "date": "28", "status": "avail", "slotCount": 5},
    ],
    "slotsByDay": {
        "d5": [
            {"id": "s1", "time": "09:00", "verifier": "S. Mehra", "rating": 4.9, "duration": 60},
            {"id": "s2", "time": "10:30", "verifier": "D. Krishnan", "rating": 4.8, "duration": 60},
            {"id": "s3", "time": "13:00", "verifier": "R. Kapoor", "rating": 4.9, "duration": 60},
            {"id": "s4", "time": "15:30", "verifier": "S. Mehra", "rating": 4.9, "duration": 60},
            {"id": "s5", "time": "17:00", "verifier": "J. Okafor", "rating": 4.7, "duration": 60},
        ]
    },
}

LIVE_SESSION: dict = {
    "id": "KAF-88421",
    "catalogId": "KAF-204",
    "skill": "Kafka & Event Streams",
    "status": "live",
    "elapsedSeconds": 23 * 60 + 47,
    "candidate": {"name": "Aarav Rao", "initials": "A", "color": "#8B2A2A"},
    "verifier": {"name": "Deepa Krishnan", "initials": "D", "color": "#4A6B3E"},
    "transcript": [
        {"t": "00:22:11", "who": "AARAV", "text": "So if the partition key is user_id, per-user ordering is preserved. Across users — no guarantee."},
        {"t": "00:22:26", "who": "DEEPA", "text": "Good. What if you add a second consumer and rebalance mid-transaction?"},
        {"t": "00:22:40", "who": "AARAV", "text": "…with transactional producer, the new consumer reads from committed offset only. Uncommitted transactions are discarded."},
        {"t": "00:22:58", "who": "DEEPA", "text": "What about the in-flight producer? Does it get fenced?"},
        {"t": "00:23:10", "who": "AARAV", "text": "…I think the broker fences the old producer epoch but I'm not 100% sure of the mechanism."},
    ],
    "phases": [
        {"num": "01", "title": "Warm-up", "done": True, "active": False},
        {"num": "02", "title": "Context & production scale", "done": True, "active": False},
        {"num": "03", "title": "Partitioning deep-dive", "done": False, "active": True},
        {"num": "04", "title": "Whiteboard: exactly-once", "done": False, "active": False},
        {"num": "05", "title": "Retrospective", "done": False, "active": False},
    ],
    "currentProbe": "How would consumer rebalance affect in-flight transactions? Walk through the sequence.",
    "assessment": [
        {"label": "Partitioning", "value": 92, "tag": "strong"},
        {"label": "Ordering semantics", "value": 78, "tag": "solid"},
        {"label": "Exactly-once", "value": 62, "tag": "partial"},
        {"label": "Operational scale", "value": 0, "tag": "unexplored"},
    ],
    "suggestedProbes": [
        "Ask about a real rebalance incident — vague on ops details",
        "Probe read_committed vs read_uncommitted tradeoff",
        "Check: schema evolution with backward compatibility",
    ],
    "unverifiedClaim": {
        "text": 'Candidate said "handled 3M events/sec" at 00:18:42. Consider asking for the architecture that supported this.',
        "at": "00:18:42",
    },
}

MY_INTERVIEWS: list[dict] = [
    {"id": "int_001", "catalog_id": "KAF-204", "title": "Kafka & Event Streams", "status": "completed", "scheduled_date": "2026-04-26T10:30:00.000Z"},
    {"id": "int_002", "catalog_id": "DOT-101", "title": ".NET Microservices", "status": "completed", "scheduled_date": "2026-03-14T15:00:00.000Z"},
    {"id": "int_003", "catalog_id": "SYS-110", "title": "System Design", "status": "completed", "scheduled_date": "2026-02-02T11:00:00.000Z"},
]


async def seed_portal() -> int:
    db = get_database()
    inserted = 0

    privacy = db["privacy_settings"]
    for item in PRIVACY_SEEDS:
        if not await privacy.find_one({"userId": item["userId"]}):
            await privacy.insert_one(dict(item))
            inserted += 1

    dossiers = db["dossiers"]
    if not await dossiers.find_one({"id": DOSSIER["id"]}):
        await dossiers.insert_one(dict(DOSSIER))
        inserted += 1

    catalogs = db["booking_catalogs"]
    if not await catalogs.find_one({"catalogId": BOOKING_CATALOG["catalogId"]}):
        await catalogs.insert_one(dict(BOOKING_CATALOG))
        inserted += 1

    sessions = db["live_sessions"]
    if not await sessions.find_one({"id": LIVE_SESSION["id"]}):
        await sessions.insert_one(dict(LIVE_SESSION))
        inserted += 1

    interviews = db["my_interviews"]
    for item in MY_INTERVIEWS:
        if not await interviews.find_one({"id": item["id"]}):
            await interviews.insert_one(dict(item))
            inserted += 1

    return inserted
