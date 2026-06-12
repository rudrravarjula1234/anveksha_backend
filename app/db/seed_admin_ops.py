"""Admin ops seed data — mirror of the frontend mock seeds.

Sources (transcribed verbatim):
- anveksha_ui/src/mocks/data/admin.ts          (dashboard, users, simple
  bots, simple feature flags, role permissions)
- anveksha_ui/src/mocks/data/adminWorkflow.ts  (overview, dossiers, slots,
  verifiers, candidates, companies, integrity, analytics)
- anveksha_ui/src/mocks/data/featureFlags.ts   (FEATURE_REGISTRY + defaults)
- anveksha_ui/src/mocks/data/rbac.ts           (ROLE_PERMISSIONS,
  CUSTOM_ROLES, AUDIT_LOG)
- anveksha_ui/src/mocks/data/pilotsFull.ts     (pilot programs + students)

Singletons (dashboard, overview, integrity signals, analytics, flag
registry, flag state) are stored as one document each with
`key: "default"`. Pilots are stored once in `pilot_programs` with the
FULL shape; `/api/admin/pilots` projects away `dept`/`assessments`
(the admin.ts values are identical to the pilotsFull.ts ones).
"""

from app.db.mongo import get_database

# ─── Dashboard (admin.ts → adminDashboard) ──────────────────────────────

DASHBOARD: dict = {
    "key": "default",
    "totalUsers": 3102,
    "activeCandidates": 2847,
    "activeVerifiers": 186,
    "activeCompanies": 94,
    "sessionsToday": 24,
    "reportsThisWeek": 312,
}

# ─── Users (admin.ts → adminUsers) ──────────────────────────────────────

ADMIN_USERS: list[dict] = [
    {
        "id": "usr_cand_001",
        "email": "aarav.rao@anveksha.dev",
        "name": "Aarav Rao",
        "roles": ["candidate"],
        "is_active": True,
        "created_at": "2025-08-12T09:00:00.000Z",
        "last_login": "2026-04-26T11:00:00.000Z",
    },
    {
        "id": "usr_ver_001",
        "email": "deepa.krishnan@anveksha.dev",
        "name": "Deepa Krishnan",
        "roles": ["interviewer"],
        "is_active": True,
        "created_at": "2025-07-20T09:00:00.000Z",
        "last_login": "2026-04-27T08:00:00.000Z",
    },
    {
        "id": "usr_co_001",
        "email": "priya.menon@northstack.co",
        "name": "Priya Menon",
        "roles": ["company", "hr"],
        "is_active": True,
        "created_at": "2025-06-15T09:00:00.000Z",
        "last_login": "2026-04-25T14:00:00.000Z",
    },
    {
        "id": "usr_co_002",
        "email": "rohan.shah@northstack.co",
        "name": "Rohan Shah",
        "roles": ["hr"],
        "is_active": True,
        "created_at": "2025-06-15T09:00:00.000Z",
        "last_login": "2026-04-25T15:00:00.000Z",
    },
    {
        "id": "usr_adm_001",
        "email": "admin@anveksha.dev",
        "name": "Tatvo Admin",
        "roles": ["admin"],
        "is_active": True,
        "created_at": "2025-01-01T09:00:00.000Z",
        "last_login": "2026-04-27T07:00:00.000Z",
    },
]

# ─── Bots — SIMPLE shape (admin.ts → bots) ──────────────────────────────
#
# Distinct from the BotFull registry served at /api/admin/bots (collection
# `bots`); these live in `bots_simple` and back GET/POST /api/bots.

SIMPLE_BOTS: list[dict] = [
    {
        "id": "BOT-001",
        "name": "Bob",
        "description": "Senior microservices architect bot. Direct, probing style.",
        "type": "interviewer",
        "model": "claude-sonnet-4-5",
        "status": "active",
        "sessionsRun": 142,
        "avgRating": 4.6,
        "createdAt": "2025-09-01T00:00:00.000Z",
    },
    {
        "id": "BOT-002",
        "name": "Rajesh",
        "description": "Azure Solution Architect. Methodical. Tradeoff-first.",
        "type": "interviewer",
        "model": "claude-opus-4-7",
        "status": "active",
        "sessionsRun": 98,
        "avgRating": 4.5,
        "createdAt": "2025-09-12T00:00:00.000Z",
    },
    {
        "id": "BOT-003",
        "name": "Priya",
        "description": "Kafka and streaming specialist. Production-first.",
        "type": "interviewer",
        "model": "claude-opus-4-7",
        "status": "active",
        "sessionsRun": 203,
        "avgRating": 4.7,
        "createdAt": "2025-08-21T00:00:00.000Z",
    },
    {
        "id": "BOT-004",
        "name": "David",
        "description": "Postgres database internals. EXPLAIN-ANALYZE-driven.",
        "type": "interviewer",
        "model": "gpt-4o",
        "status": "active",
        "sessionsRun": 87,
        "avgRating": 4.4,
        "createdAt": "2025-10-04T00:00:00.000Z",
    },
    {
        "id": "BOT-005",
        "name": "Amara",
        "description": "Payments + idempotency. Scenario-based.",
        "type": "interviewer",
        "model": "claude-opus-4-7",
        "status": "active",
        "sessionsRun": 54,
        "avgRating": 4.8,
        "createdAt": "2025-11-11T00:00:00.000Z",
    },
    {
        "id": "BOT-006",
        "name": "Sam",
        "description": "Frontend / React architecture.",
        "type": "interviewer",
        "model": "gpt-4o",
        "status": "draft",
        "sessionsRun": 12,
        "avgRating": 4.2,
        "createdAt": "2026-02-01T00:00:00.000Z",
    },
]

# ─── Feature flags — simple list (admin.ts → featureFlags) ──────────────

SIMPLE_FEATURE_FLAGS: list[dict] = [
    {"key": "candidate.public_profile", "name": "Public Profile", "description": "Shareable profile page with skill constellation", "enabled": True, "scope": "candidate"},
    {"key": "candidate.privacy_controls", "name": "Privacy & Sharing", "description": "Granular controls over what companies can see", "enabled": True, "scope": "candidate"},
    {"key": "assessment.live_sessions", "name": "Live (Human) Sessions", "description": "1:1 sessions with a specialist verifier", "enabled": True, "scope": "global"},
    {"key": "assessment.bot_sessions", "name": "Bot Sessions (Instant)", "description": "Fully automated AI assessment", "enabled": True, "scope": "global"},
    {"key": "company.ai_chat", "name": "AI Investigate (Claude)", "description": "Live Claude chat grounded in session evidence", "enabled": True, "scope": "company"},
    {"key": "company.gray_followups", "name": "Gray Follow-up Requests", "description": "Companies can trigger Gray verifications", "enabled": True, "scope": "company"},
    {"key": "verifier.anonymous_queue", "name": "Anonymous Candidate IDs", "description": "Hide candidate identity from verifiers until session", "enabled": True, "scope": "verifier"},
    {"key": "ai.transcript_analysis", "name": "Transcript Analysis", "description": "AI analyses session transcripts for Gap/Gray", "enabled": True, "scope": "global"},
    {"key": "admin.impersonate", "name": "Company Impersonation", "description": "Admin can log in as a company for support", "enabled": False, "scope": "global"},
]

# ─── Role permissions — simple list (admin.ts → rolePermissions) ────────

ROLE_PERMISSIONS_SIMPLE: list[dict] = [
    {"role": "candidate", "permissions": ["view_own_dossier", "book_session", "share_dossier", "manage_privacy"]},
    {"role": "interviewer", "permissions": ["view_queue", "join_session", "submit_report", "view_governance"]},
    {"role": "company", "permissions": ["search_candidates", "view_pipeline", "chat_dossier", "request_followup"]},
    {"role": "hr", "permissions": ["search_candidates", "view_pipeline", "invite_members"]},
    {"role": "admin", "permissions": ["*"]},
]

# ─── Overview (adminWorkflow.ts → overviewStats + overviewActivity) ─────

OVERVIEW: dict = {
    "key": "default",
    "stats": [
        {"label": "Sessions today", "value": 24, "sub": "↑ 8 vs yesterday", "color": "oxblood"},
        {"label": "Published dossiers", "value": 2847, "sub": "of 3,102 total"},
        {"label": "Active verifiers", "value": 186, "sub": "12 new this month"},
        {"label": "Company accounts", "value": 94, "sub": "8 enterprise seats"},
        {"label": "Gray signals (30d)", "value": 1204, "sub": "↑ 18% MoM"},
        {"label": "Integrity flags (30d)", "value": 12, "sub": "3 confirmed fraud"},
    ],
    "activity": [
        {"id": "act_1", "text": "RAW-S-9941 created · Aarav Rao + D. Krishnan", "time": "2m ago", "tone": "oxblood"},
        {"id": "act_2", "text": "SVR-KAF-88421 published by D. Krishnan", "time": "1h ago", "tone": "verdant"},
        {"id": "act_3", "text": "Voice biometric mismatch · SVR-8811", "time": "3h ago", "tone": "ochre"},
        {"id": "act_4", "text": "New company account · TechCorp India", "time": "5h ago", "tone": "sky"},
        {"id": "act_5", "text": "K. Okonkwo approved as Kafka verifier", "time": "Yesterday", "tone": "ink"},
        {"id": "act_6", "text": "Session SVR-8721 confirmed fraud · blacklisted", "time": "2d ago", "tone": "oxblood"},
    ],
}

# ─── Dossiers (adminWorkflow.ts → dossiersSeed) ─────────────────────────

DOSSIERS: list[dict] = [
    {"id": "SVR-KAF-88421", "candidate": "Aarav Rao", "skill": "Kafka & Event Streams", "verifier": "D. Krishnan", "date": "Apr 26", "score": 76, "status": "published"},
    {"id": "SVR-NET-65433", "candidate": "Aarav Rao", "skill": ".NET Microservices", "verifier": "S. Mehra", "date": "Mar 14", "score": 87, "status": "published"},
    {"id": "SVR-SYS-72110", "candidate": "Aarav Rao", "skill": "System Design", "verifier": "M. Patel", "date": "Feb 02", "score": 82, "status": "published"},
    {"id": "SVR-PAY-91001", "candidate": "Priya Nair", "skill": "Payments System Design", "verifier": "S. Mehra", "date": "Apr 20", "score": 0, "status": "draft"},
    {"id": "SVR-NET-88003", "candidate": "Omar Haddad", "skill": ".NET Microservices", "verifier": "S. Mehra", "date": "Apr 26", "score": 0, "status": "in-review"},
    {"id": "SVR-PG-51200", "candidate": "Aarav Rao", "skill": "Postgres & Indexing", "verifier": "R. Kapoor", "date": "Jan 18", "score": 78, "status": "published"},
]

# ─── Slots (adminWorkflow.ts → slotsSeed) ───────────────────────────────

ADMIN_SLOTS: list[dict] = [
    {"id": "slt_1", "verifier": "D. Krishnan", "day": "Mon Apr 21", "time": "09:00", "duration": 60, "skill": "Kafka", "booked": True, "candidate": "Priya Nair"},
    {"id": "slt_2", "verifier": "D. Krishnan", "day": "Mon Apr 21", "time": "14:00", "duration": 90, "skill": "System Design", "booked": False},
    {"id": "slt_3", "verifier": "S. Mehra", "day": "Mon Apr 21", "time": "11:00", "duration": 60, "skill": ".NET", "booked": True, "candidate": "Omar Haddad"},
    {"id": "slt_4", "verifier": "S. Mehra", "day": "Tue Apr 22", "time": "10:00", "duration": 60, "skill": "Any", "booked": False},
    {"id": "slt_5", "verifier": "R. Kapoor", "day": "Wed Apr 23", "time": "09:00", "duration": 60, "skill": "Postgres", "booked": False},
    {"id": "slt_6", "verifier": "M. Patel", "day": "Thu Apr 24", "time": "11:00", "duration": 90, "skill": "System Design", "booked": False},
    {"id": "slt_7", "verifier": "J. Okafor", "day": "Fri Apr 25", "time": "14:00", "duration": 60, "skill": "Cloud", "booked": True, "candidate": "Li Wei"},
]

# ─── Verifiers (adminWorkflow.ts → verifiersSeed) ───────────────────────

ADMIN_VERIFIERS: list[dict] = [
    {"id": "v_001", "name": "D. Krishnan", "specialization": "Kafka · Systems", "sessions": 247, "rating": 4.9, "quality": "Exemplary", "since": "Jan 2025", "tier": "active"},
    {"id": "v_002", "name": "S. Mehra", "specialization": ".NET · Microservices", "sessions": 183, "rating": 4.9, "quality": "Exemplary", "since": "Mar 2025", "tier": "active"},
    {"id": "v_003", "name": "R. Kapoor", "specialization": "Postgres · DBs", "sessions": 142, "rating": 4.8, "quality": "Strong", "since": "Feb 2025", "tier": "active"},
    {"id": "v_004", "name": "M. Patel", "specialization": "System Design", "sessions": 98, "rating": 4.7, "quality": "Strong", "since": "Jun 2025", "tier": "active"},
    {"id": "v_005", "name": "J. Okafor", "specialization": "Cloud · AWS", "sessions": 76, "rating": 4.8, "quality": "Strong", "since": "Aug 2025", "tier": "active"},
    {"id": "v_a01", "name": "K. Okonkwo", "specialization": "Kafka · Streaming", "sessions": 0, "rating": 0, "quality": "Strong", "since": "—", "tier": "applicants", "experience": "8 yrs · ex-Confluent", "applied": "Apr 18", "sample": "Reviewed"},
    {"id": "v_a02", "name": "A. Sharma", "specialization": "React · Frontend", "sessions": 0, "rating": 0, "quality": "Strong", "since": "—", "tier": "applicants", "experience": "6 yrs · ex-Razorpay", "applied": "Apr 17", "sample": "Pending"},
    {"id": "v_a03", "name": "P. Wong", "specialization": "Go · Distributed", "sessions": 0, "rating": 0, "quality": "Strong", "since": "—", "tier": "applicants", "experience": "10 yrs · ex-Google", "applied": "Apr 15", "sample": "Reviewed"},
]

# ─── Candidates (adminWorkflow.ts → adminCandidatesSeed) ────────────────

ADMIN_CANDIDATES: list[dict] = [
    {"id": "c_001", "name": "Aarav Rao", "location": "Bengaluru", "verifications": 5, "topScore": 79, "lastSession": "Apr 26", "status": "active"},
    {"id": "c_002", "name": "Priya Nair", "location": "Pune", "verifications": 3, "topScore": 88, "lastSession": "Apr 20", "status": "active"},
    {"id": "c_003", "name": "Omar Haddad", "location": "Dubai", "verifications": 2, "topScore": 71, "lastSession": "Apr 26", "status": "active"},
    {"id": "c_004", "name": "Li Wei", "location": "Singapore", "verifications": 4, "topScore": 92, "lastSession": "Apr 18", "status": "active"},
    {"id": "c_005", "name": "Amara Diallo", "location": "Lagos", "verifications": 1, "topScore": 68, "lastSession": "Apr 12", "status": "active"},
    {"id": "c_006", "name": "S. Blocked", "location": "Mumbai", "verifications": 1, "topScore": 0, "lastSession": "Mar 10", "status": "blacklisted"},
]

# ─── Companies (adminWorkflow.ts → adminCompaniesSeed) ──────────────────

ADMIN_COMPANIES: list[dict] = [
    {"id": "co_001", "name": "NorthStack", "plan": "Enterprise", "seats": 25, "seatsUsed": 12, "chats": 487, "followups": 3, "since": "Jan 2026", "status": "active"},
    {"id": "co_002", "name": "Razorpay", "plan": "Growth", "seats": 10, "seatsUsed": 7, "chats": 210, "followups": 4, "since": "Feb 2026", "status": "active"},
    {"id": "co_003", "name": "Meesho", "plan": "Growth", "seats": 10, "seatsUsed": 3, "chats": 88, "followups": 2, "since": "Mar 2026", "status": "active"},
    {"id": "co_004", "name": "TechCorp India", "plan": "Starter", "seats": 3, "seatsUsed": 1, "chats": 12, "followups": 1, "since": "Apr 2026", "status": "trial"},
    {"id": "co_005", "name": "OldCo", "plan": "Starter", "seats": 3, "seatsUsed": 0, "chats": 0, "followups": 0, "since": "Nov 2025", "status": "churned"},
]

# ─── Integrity (adminWorkflow.ts → integrityFlagsSeed + signals) ────────

INTEGRITY_FLAGS: list[dict] = [
    {"id": "flag_1", "summary": "Voice biometric mismatch · candidate voice changed mid-session", "refId": "SVR-8811", "severity": "high", "date": "Apr 24", "action": "Suspend dossier"},
    {"id": "flag_2", "summary": "Unusual response latency — avg 12s per answer (expected 2–4s)", "refId": "SVR-8798", "severity": "medium", "date": "Apr 24", "action": "Flag for review"},
    {"id": "flag_3", "summary": "Verifier scoring drift — 3σ above mean score this week", "refId": "V-042", "severity": "medium", "date": "Apr 23", "action": "Verifier warning"},
    {"id": "flag_4", "summary": "Screen-share anomaly — off-screen gaze detected 14 times", "refId": "SVR-8751", "severity": "high", "date": "Apr 22", "action": "Manual review"},
    {"id": "flag_5", "summary": "Lookup behavior confirmed — candidate blacklisted", "refId": "SVR-8721", "severity": "confirmed", "date": "Apr 21", "action": "Resolved"},
]

INTEGRITY_SIGNALS: dict = {
    "key": "default",
    "signals": [
        {"id": "sig_1", "name": "Voice biometric baseline", "status": "Active · 186 verifiers enrolled"},
        {"id": "sig_2", "name": "Response latency analysis", "status": "Active · flags > 2σ deviation"},
        {"id": "sig_3", "name": "Screen-share gaze tracking", "status": "Active · per-session"},
        {"id": "sig_4", "name": "Verifier score drift", "status": "Active · weekly audit"},
        {"id": "sig_5", "name": "Transcript vs audio match", "status": "Active · NLP comparison"},
        {"id": "sig_6", "name": "Candidate reuse detection", "status": "Active · voice + face"},
    ],
}

# ─── Analytics (adminWorkflow.ts → analyticsData) ───────────────────────

ANALYTICS: dict = {
    "key": "default",
    "topStats": [
        {"label": "Sessions MoM growth", "value": "+11.7%", "color": "verdant"},
        {"label": "Dossier → hire rate", "value": "34%", "sub": "industry: 8% traditional"},
        {"label": "AI / verifier score Δ", "value": "±3.2", "sub": "avg score delta"},
        {"label": "NPS", "value": "72", "sub": "candidate NPS · 81"},
    ],
    "months": ["Nov", "Dec", "Jan", "Feb", "Mar", "Apr"],
    "sessions": [180, 224, 312, 348, 401, 448],
    "topSkills": [
        {"name": "System Design", "share": 38},
        {"name": "Kafka & Streaming", "share": 27},
        {"name": "Microservices", "share": 18},
        {"name": ".NET / C#", "share": 12},
        {"name": "Postgres Internals", "share": 9},
        {"name": "Payments Domain", "share": 7},
    ],
}

# ─── Feature registry + state (featureFlags.ts) ─────────────────────────

FEATURE_REGISTRY: list[dict] = [
    {
        "group": "Candidate Portal",
        "flags": [
            {"id": "candidate.public_profile", "label": "Public Profile", "desc": "Shareable profile page with skill constellation and timeline.", "default": True},
            {"id": "candidate.insights", "label": "My Insights", "desc": "Gray-triggered personal assessment suggestions.", "default": True},
            {"id": "candidate.privacy_controls", "label": "Privacy & Sharing", "desc": "Granular controls over what companies can see.", "default": True},
            {"id": "candidate.skill_reports", "label": "Skill Reports", "desc": "Access to completed assessment output reports.", "default": True},
            {"id": "candidate.onboarding", "label": "Guided Onboarding", "desc": "4-step onboarding flow for new candidates.", "default": True},
            {"id": "candidate.notifications", "label": "Notifications", "desc": "In-platform notification centre.", "default": True},
        ],
    },
    {
        "group": "Assessments & Sessions",
        "flags": [
            {"id": "assessment.live_sessions", "label": "Live (Human) Sessions", "desc": "1:1 sessions with a specialist verifier.", "default": True},
            {"id": "assessment.bot_sessions", "label": "Bot Sessions (Instant)", "desc": "Fully automated AI assessment — no scheduling.", "default": True},
            {"id": "assessment.bot_assisted", "label": "Bot-Assisted Sessions", "desc": "AI-led session with human verifier sign-off.", "default": True},
            {"id": "assessment.coupons", "label": "Coupons & Discounts", "desc": "Coupon codes for assessment pricing.", "default": True},
            {"id": "assessment.paid", "label": "Paid Assessments", "desc": "Allow assessments with ₹ price. Disable to make everything free.", "default": True},
            {"id": "assessment.catalog_public", "label": "Public Catalog", "desc": "Candidates can browse the catalog without logging in.", "default": False},
        ],
    },
    {
        "group": "Company Portal",
        "flags": [
            {"id": "company.discover", "label": "NL Candidate Discovery", "desc": "Natural-language search for candidates.", "default": True},
            {"id": "company.ai_chat", "label": "AI Investigate (Claude)", "desc": "Live Claude chat grounded in session evidence.", "default": True},
            {"id": "company.candidate_unlock", "label": "Candidate Unlock (₹499)", "desc": "Paid identity reveal for locked candidates.", "default": True},
            {"id": "company.gray_followups", "label": "Gray Follow-up Requests", "desc": "Companies can trigger targeted assessments on Gray areas.", "default": True},
            {"id": "company.pipeline", "label": "Pipeline (Kanban)", "desc": "Kanban-style candidate pipeline management.", "default": True},
            {"id": "company.team_seats", "label": "Team & Seats Management", "desc": "Multi-member company accounts with seat control.", "default": True},
        ],
    },
    {
        "group": "Verifier Portal",
        "flags": [
            {"id": "verifier.slot_creator", "label": "Slot Creator (Calendar)", "desc": "Verifiers can create and manage their own availability slots.", "default": True},
            {"id": "verifier.earnings", "label": "Earnings Dashboard", "desc": "Verifier payout history and rate card.", "default": True},
            {"id": "verifier.ai_copilot", "label": "AI Co-pilot (RAW)", "desc": "AI probe suggestions and live scoring during RAW sessions.", "default": True},
            {"id": "verifier.anonymous_queue", "label": "Anonymous Candidate IDs", "desc": "Hide candidate identity from verifiers until session starts.", "default": True},
        ],
    },
    {
        "group": "AI & Bots",
        "flags": [
            {"id": "ai.bot_registry", "label": "Bot Registry", "desc": "Admin can create and manage AI verifier personas.", "default": True},
            {"id": "ai.model_registry", "label": "Model Registry", "desc": "Admin can configure LLM endpoints, API keys, and fallback chains.", "default": True},
            {"id": "ai.live_claude_chat", "label": "Live Claude in AI Chat", "desc": "Company AI Investigate uses real Claude API calls.", "default": True},
            {"id": "ai.transcript_analysis", "label": "Transcript Analysis", "desc": "AI analyses session transcripts to generate Gap/Gray/Summary.", "default": True},
        ],
    },
    {
        "group": "Pilot Programs",
        "flags": [
            {"id": "pilot.programs", "label": "Pilot Programs", "desc": "College/cohort-based verification programs.", "default": True},
            {"id": "pilot.bulk_import", "label": "Bulk CSV Import", "desc": "Admin can bulk-register students via CSV.", "default": True},
            {"id": "pilot.analytics", "label": "Pilot Analytics", "desc": "Completion and score distribution reports per pilot.", "default": True},
        ],
    },
    {
        "group": "Admin Controls",
        "flags": [
            {"id": "admin.integrity", "label": "Integrity Dashboard", "desc": "Fraud detection, voice biometrics, session anomaly alerts.", "default": True},
            {"id": "admin.analytics", "label": "Platform Analytics", "desc": "Sessions chart, skill volumes, NPS.", "default": True},
            {"id": "admin.impersonate", "label": "Company Impersonation", "desc": "Admin can log in as a company account for support.", "default": False},
            {"id": "admin.verifier_invites", "label": "Verifier Invite System", "desc": "Admin can invite special verifiers (architects, trusted).", "default": True},
        ],
    },
]


def default_flag_state(registry: list[dict] | None = None) -> dict[str, bool]:
    """Mirror of featureFlags.ts `defaultFlagState()`."""
    result: dict[str, bool] = {}
    for group in registry if registry is not None else FEATURE_REGISTRY:
        for flag in group["flags"]:
            result[flag["id"]] = flag["default"]
    return result


# ─── RBAC (rbac.ts) ─────────────────────────────────────────────────────

RBAC_ROLES: list[dict] = [
    {
        "id": "candidate",
        "label": "Candidate",
        "color": "var(--oxblood)",
        "perms": [
            {"id": "view_own_profile", "label": "View own profile", "on": True, "locked": True},
            {"id": "view_assessments", "label": "Browse assessment catalog", "on": True, "locked": True},
            {"id": "book_session", "label": "Book a session", "on": True, "locked": False},
            {"id": "view_own_reports", "label": "View own Skill Reports", "on": True, "locked": True},
            {"id": "share_profile", "label": "Share public profile", "on": True, "locked": False},
            {"id": "control_privacy", "label": "Control privacy settings", "on": True, "locked": False},
            {"id": "view_insights", "label": "View Insights", "on": True, "locked": False},
            {"id": "accept_followup", "label": "Accept / decline follow-ups", "on": True, "locked": False},
            {"id": "view_other_candidates", "label": "View other candidates", "on": False, "locked": True},
            {"id": "view_company_data", "label": "View company data", "on": False, "locked": True},
            {"id": "admin_access", "label": "Admin access", "on": False, "locked": True},
        ],
    },
    {
        "id": "verifier",
        "label": "Verifier",
        "color": "var(--ink)",
        "perms": [
            {"id": "run_sessions", "label": "Conduct verification sessions", "on": True, "locked": True},
            {"id": "write_reports", "label": "Write & publish reports", "on": True, "locked": True},
            {"id": "manage_own_slots", "label": "Manage own slots", "on": True, "locked": True},
            {"id": "view_session_transcript", "label": "View session transcripts", "on": True, "locked": True},
            {"id": "view_candidate_name", "label": "View candidate name during session", "on": True, "locked": False},
            {"id": "view_earnings", "label": "View earnings dashboard", "on": True, "locked": False},
            {"id": "view_other_verifier_data", "label": "View other verifier data", "on": False, "locked": True},
            {"id": "candidate_portal", "label": "Own candidate portal (dual-role)", "on": True, "locked": False},
            {"id": "admin_access", "label": "Admin access", "on": False, "locked": True},
        ],
    },
    {
        "id": "company",
        "label": "Company",
        "color": "var(--sky)",
        "perms": [
            {"id": "search_candidates", "label": "Search candidate pool", "on": True, "locked": True},
            {"id": "unlock_candidates", "label": "Unlock candidate identity", "on": True, "locked": False},
            {"id": "ai_chat", "label": "AI Investigate (chat)", "on": True, "locked": False},
            {"id": "request_followup", "label": "Request Gray follow-up", "on": True, "locked": False},
            {"id": "view_skill_report", "label": "View candidate Skill Reports", "on": True, "locked": True},
            {"id": "view_transcript", "label": "View session transcripts", "on": False, "locked": False},
            {"id": "manage_team", "label": "Manage team seats", "on": True, "locked": False},
            {"id": "export_data", "label": "Export candidate data", "on": False, "locked": False},
            {"id": "admin_access", "label": "Admin access", "on": False, "locked": True},
        ],
    },
    {
        "id": "admin",
        "label": "Admin",
        "color": "#5B3E8F",
        "perms": [
            {"id": "manage_assessments", "label": "Manage assessment catalog", "on": True, "locked": True},
            {"id": "manage_bots", "label": "Manage bots", "on": True, "locked": True},
            {"id": "manage_models", "label": "Manage model registry", "on": True, "locked": True},
            {"id": "manage_verifiers", "label": "Approve / manage verifiers", "on": True, "locked": True},
            {"id": "manage_companies", "label": "Manage company accounts", "on": True, "locked": True},
            {"id": "view_integrity", "label": "View integrity dashboard", "on": True, "locked": True},
            {"id": "manage_feature_flags", "label": "Manage feature flags", "on": True, "locked": True},
            {"id": "manage_rbac", "label": "Manage RBAC", "on": True, "locked": True},
            {"id": "impersonate_accounts", "label": "Impersonate accounts", "on": False, "locked": False},
            {"id": "delete_reports", "label": "Delete published reports", "on": False, "locked": False},
            {"id": "bulk_operations", "label": "Bulk data operations", "on": True, "locked": False},
        ],
    },
]

CUSTOM_ROLES: list[dict] = [
    {
        "id": "CR-001",
        "name": "Pilot Coordinator",
        "baseRole": "admin",
        "desc": "College coordinators managing pilot programs. No access to production candidate data.",
        "members": 3,
        "overrides": {
            "manage_assessments": False,
            "manage_bots": False,
            "manage_models": False,
            "manage_companies": False,
            "view_integrity": False,
            "impersonate_accounts": False,
        },
    },
    {
        "id": "CR-002",
        "name": "Content Reviewer",
        "baseRole": "admin",
        "desc": "Reviews AI-generated report drafts. Cannot publish.",
        "members": 2,
        "overrides": {"manage_verifiers": False, "manage_companies": False, "view_integrity": False},
    },
    {
        "id": "CR-003",
        "name": "Trusted Verifier",
        "baseRole": "verifier",
        "desc": "Senior practitioner invited by admin. Gets early access to new assessment types.",
        "members": 8,
        "overrides": {},
    },
]

AUDIT_LOG: list[dict] = [
    {"id": "a1", "time": "2h ago", "actor": "Admin · Ravi Gupta", "action": "Toggled feature flag", "detail": "candidate.public_profile → ON"},
    {"id": "a2", "time": "5h ago", "actor": "Admin · Ravi Gupta", "action": "Updated role permission", "detail": "company.view_transcript → ON"},
    {"id": "a3", "time": "Yesterday", "actor": "Admin · Priya Menon", "action": "Created custom role", "detail": "Pilot Coordinator (CR-001)"},
    {"id": "a4", "time": "Apr 24", "actor": "Admin · Ravi Gupta", "action": "Toggled feature flag", "detail": "admin.impersonate → OFF"},
    {"id": "a5", "time": "Apr 23", "actor": "Admin · Priya Menon", "action": "Bulk disabled flags", "detail": "Pilot Programs group → all OFF (maintenance)"},
    {"id": "a6", "time": "Apr 22", "actor": "Admin · Ravi Gupta", "action": "Assigned custom role", "detail": "3 users → Pilot Coordinator"},
]

# ─── Pilots (pilotsFull.ts — superset of admin.ts pilotPrograms) ────────

PILOT_PROGRAMS: list[dict] = [
    {
        "id": "PLT-001",
        "name": "IIT Bombay — Backend Engineering",
        "college": "IIT Bombay",
        "dept": "Computer Science",
        "batch": "2024-25",
        "coordinator": "Prof. S. Iyer",
        "status": "active",
        "students": 84,
        "completed": 61,
        "avgScore": 72,
        "startDate": "Apr 1, 2026",
        "endDate": "May 31, 2026",
        "assessments": ["ASS-001", "ASS-002", "ASS-004"],
    },
    {
        "id": "PLT-002",
        "name": "BITS Pilani — Full Stack",
        "college": "BITS Pilani",
        "dept": "Computer Science",
        "batch": "2024-25",
        "coordinator": "Prof. R. Sharma",
        "status": "active",
        "students": 52,
        "completed": 28,
        "avgScore": 68,
        "startDate": "Apr 15, 2026",
        "endDate": "Jun 15, 2026",
        "assessments": ["ASS-007", "ASS-002"],
    },
    {
        "id": "PLT-003",
        "name": "NIT Trichy — Cloud Track",
        "college": "NIT Trichy",
        "dept": "Information Technology",
        "batch": "2024-25",
        "coordinator": "Prof. A. Kumar",
        "status": "draft",
        "students": 38,
        "completed": 0,
        "avgScore": 0,
        "startDate": "May 1, 2026",
        "endDate": "Jun 30, 2026",
        "assessments": ["ASS-008"],
    },
]

PILOT_STUDENTS: list[dict] = [
    {"id": "STU-001", "name": "Arjun Mehta", "email": "arjun@iitb.ac.in", "program": "PLT-001", "completed": 2, "pending": 1, "avgScore": 78, "status": "active"},
    {"id": "STU-002", "name": "Priya Suresh", "email": "priya@iitb.ac.in", "program": "PLT-001", "completed": 3, "pending": 0, "avgScore": 84, "status": "active"},
    {"id": "STU-003", "name": "Rahul Das", "email": "rahul@iitb.ac.in", "program": "PLT-001", "completed": 1, "pending": 2, "avgScore": 65, "status": "active"},
    {"id": "STU-004", "name": "Anjali Singh", "email": "anjali@iitb.ac.in", "program": "PLT-001", "completed": 0, "pending": 3, "avgScore": 0, "status": "registered"},
    {"id": "STU-005", "name": "Karan Patel", "email": "karan@bits.ac.in", "program": "PLT-002", "completed": 2, "pending": 1, "avgScore": 71, "status": "active"},
    {"id": "STU-006", "name": "Meena Rajan", "email": "meena@bits.ac.in", "program": "PLT-002", "completed": 1, "pending": 2, "avgScore": 69, "status": "active"},
]

# ─── Seeder ─────────────────────────────────────────────────────────────

_SINGLETONS: list[tuple[str, dict]] = [
    ("admin_dashboard", DASHBOARD),
    ("admin_overview", OVERVIEW),
    ("integrity_signals", INTEGRITY_SIGNALS),
    ("admin_analytics", ANALYTICS),
    ("admin_flag_registry", {"key": "default", "registry": FEATURE_REGISTRY}),
    ("admin_flag_state", {"key": "default", "state": default_flag_state()}),
]

# (collection, id field, templates)
_COLLECTIONS: list[tuple[str, str, list[dict]]] = [
    ("admin_users", "id", ADMIN_USERS),
    ("bots_simple", "id", SIMPLE_BOTS),
    ("admin_feature_flags", "key", SIMPLE_FEATURE_FLAGS),
    ("admin_role_permissions", "role", ROLE_PERMISSIONS_SIMPLE),
    ("admin_dossiers", "id", DOSSIERS),
    ("admin_slots", "id", ADMIN_SLOTS),
    ("admin_verifiers", "id", ADMIN_VERIFIERS),
    ("admin_candidates", "id", ADMIN_CANDIDATES),
    ("admin_companies", "id", ADMIN_COMPANIES),
    ("integrity_flags", "id", INTEGRITY_FLAGS),
    ("rbac_roles", "id", RBAC_ROLES),
    ("rbac_custom_roles", "id", CUSTOM_ROLES),
    ("rbac_audit", "id", AUDIT_LOG),
    ("pilot_programs", "id", PILOT_PROGRAMS),
    ("pilot_students", "id", PILOT_STUDENTS),
]


async def seed_admin_ops() -> int:
    """Insert any missing admin-ops seed docs. Returns how many were inserted."""
    db = get_database()
    inserted = 0

    for coll_name, template in _SINGLETONS:
        coll = db[coll_name]
        if not await coll.find_one({"key": "default"}):
            await coll.insert_one(dict(template))
            inserted += 1

    for coll_name, id_field, templates in _COLLECTIONS:
        coll = db[coll_name]
        for item in templates:
            if not await coll.find_one({id_field: item[id_field]}):
                await coll.insert_one(dict(item))
                inserted += 1

    return inserted
