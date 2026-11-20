r"""Real candidate data for the demo's logged-in Google user
rudrravarjula1234@gmail.com == usr_g_01M7TH79WNDCBB4E9REWWDK85Z (Sai Rajesh).

Without a skill_ledger of their own the candidate portal falls back to
_FALLBACK_USER (Aarav) and shows his mock data. This seeds a real ledger +
public profile tied to their actual verified journey (Python FastAPI,
report SVR-FASTAPI-10003), so every candidate page shows THEIR data.

Idempotent. Run:  .\.venv\Scripts\python.exe seed_user_rudrravarjula.py
"""

import asyncio
import selectors
import sys

UID = "usr_g_01M7TH79WNDCBB4E9REWWDK85Z"
NAME = "Sai Rajesh Rudravarjula"


async def _main() -> None:
    from app.db.session import connect_to_db, close_db, get_sessionmaker
    from app.models.skill import SkillLedger, SkillLedgerRow
    from app.models.candidate import PublicProfile

    await connect_to_db()
    try:
        async with get_sessionmaker()() as db:
            # 1) Skill ledger (drives /candidate/profile + /api/profiles/me).
            led = await db.get(SkillLedger, UID)
            if led is None:
                led = SkillLedger(candidate_id=UID)
                db.add(led)
            led.candidate_name = NAME
            led.candidate_title = ".NET Full Stack & Agentic Architect · 8 yrs"
            led.candidate_location = "Hyderabad"
            led.candidate_initials = "SR"
            led.dossier_id = "ANV-SAI-01"
            led.verification_score = 79
            led.verified_count = 1
            led.partial_count = 0
            led.gray_count = 2
            led.top_percent = 18
            led.profile_bio = ".NET full-stack and agentic-AI architect with 8 years building distributed systems and AI agents."
            led.profile_current_role = ".NET Full Stack & Agentic Architect"
            led.profile_experience_years = 8
            led.profile_skills = [".NET", "C#", "Agentic AI", "Microservices", "Azure"]
            led.interviewer_mode = "none"
            led.external_proofs = []
            await db.flush()

            # 2) Ledger rows — one verified (real report) + two gray (demand).
            existing = {r.skill_id for r in (await db.execute(
                __import__("sqlalchemy").select(SkillLedgerRow).where(SkillLedgerRow.ledger_candidate_id == UID)
            )).scalars().all()}
            rows = [
                {"skill_id": "skl_sai_1", "name": "Python FastAPI & Async Data Systems", "state": "verified",
                 "depth": "Intermediate", "score": 79, "last_verified": "Nov 19", "sessions": 1,
                 "report_id": "SVR-FASTAPI-10003"},
                {"skill_id": "skl_sai_2", "name": "Event-Driven Backends with Kafka", "state": "gray",
                 "depth": "Not tested", "score": None, "last_verified": None, "sessions": 0, "report_id": None},
                {"skill_id": "skl_sai_3", "name": "System Design", "state": "gray",
                 "depth": "Not tested", "score": None, "last_verified": None, "sessions": 0, "report_id": None},
            ]
            for r in rows:
                if r["skill_id"] in existing:
                    continue
                db.add(SkillLedgerRow(ledger_candidate_id=UID, **r))

            # 3) Public profile.
            pp = await db.get(PublicProfile, UID)
            if pp is None:
                pp = PublicProfile(user_id=UID)
                db.add(pp)
            pp.share_url = "anveksha.dev/p/sai-rajesh"
            pp.anv_id = "ANV-SAI-01"
            pp.last_updated = "Nov 20, 2026"
            pp.headline = "Backend Engineer · Verified in Python FastAPI"
            pp.views = 0
            pp.unique_companies = 0
            pp.inbound_chats = 0
            pp.about = "Backend engineer focused on async Python services and data systems."
            pp.highlights = [{"highlight_id": "h1", "skill": "Python FastAPI & Async Data Systems", "score": 79}]
            pp.constellation = [
                {"name": "Python FastAPI", "score": 79, "state": "verified"},
                {"name": "Kafka", "score": 0, "state": "gray"},
                {"name": "System Design", "score": 0, "state": "gray"},
            ]
            pp.timeline = [
                {"entry_id": "t1", "date": "Nov 19", "skill": "Python FastAPI & Async Data Systems",
                 "score": 79, "type": "verified", "note": "Verified by Sai (SME)"},
            ]
            pp.gray_areas = [
                {"area_id": "g1", "name": "Event-Driven Backends with Kafka", "companies": 3},
                {"area_id": "g2", "name": "System Design", "companies": 2},
            ]

            await db.commit()
            print(f"Seeded real candidate data for {NAME} ({UID}).")
    finally:
        await close_db()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_main())
